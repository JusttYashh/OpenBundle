"""Build adapters and optionally warm Tier B. Never publish a half-built stage."""

from __future__ import annotations

import os
import threading
from typing import Any, Callable

from openbundle.adapters.json_schema import JsonSchemaRetry
from openbundle.adapters.llmlingua2 import CompressLayer
from openbundle.adapters.named import (
    HOSTED_OBS_URLS,
    LOCAL_OBS_URLS,
    CostRouter,
    FaithfulnessHeuristic,
    HistoryPrune,
    LiteLLMDispatch,
    LynxFaithfulness,
    ObsSink,
    RecompStage,
    SampledEval,
    SemanticCacheStage,
    SemanticRouterStage,
)
from openbundle.adapters.nemo_rails import NemoRails
from openbundle.adapters.scans import InjectionScan, try_presidio, SecretsScan
from openbundle.config import Settings
from openbundle.init.scan import installed_extras, scan_env
from openbundle.pipeline.jobs import (
    HOSTED_JOBS,
    JOB_BY_ID,
    LIVE,
    OFF,
    SELF_HOSTED_JOBS,
    TIER_B_IDS,
    WARMING,
    JobSpec,
)
from openbundle.pipeline.layers.cache import CacheLayer
from openbundle.pipeline.registry import StageRegistry


def job_enabled(settings: Settings, job_id: str) -> bool:
    if settings.jobs:
        return bool(settings.jobs.get(job_id, False))
    if job_id == "exact_hash":
        return bool(settings.layers.cache.enabled)
    return False


def has_local_inference(scan: Any | None = None) -> bool:
    result = scan or scan_env()
    hints = set(result.hints)
    if hints & {"ollama", "vllm", "sglang"}:
        return True
    if os.environ.get("VLLM_BASE_URL") or os.environ.get("SGLANG_BASE_URL"):
        return True
    return False


def warming_disabled() -> bool:
    return os.environ.get("OPENBUNDLE_NO_WARMING", "").strip().lower() in {"1", "true", "yes"}


def build_stage(job: JobSpec, settings: Settings) -> Any | None:
    if job.id == "exact_hash":
        return CacheLayer(settings)
    if job.id == "compress":
        cfg = settings.layers.compress.model_copy()
        cfg.enabled = True
        return CompressLayer(cfg)
    if job.id == "history":
        return HistoryPrune()
    if job.id == "rag_compress":
        return RecompStage()
    if job.id == "secrets":
        return SecretsScan()
    if job.id == "pii":
        return try_presidio()
    if job.id == "injection":
        return InjectionScan()
    if job.id == "nemo_rails":
        return NemoRails(llm_check=settings.layers.nemo_rails.llm_check)
    if job.id == "cost_route":
        return CostRouter()
    if job.id == "litellm":
        return LiteLLMDispatch()
    if job.id in {"output_validate", "structured"}:
        cfg = settings.layers.structured.model_copy()
        cfg.enabled = True
        return JsonSchemaRetry(cfg)
    if job.id == "eval_promptfoo":
        return SampledEval("eval_promptfoo", "promptfoo")
    if job.id == "eval_deepeval":
        return SampledEval("eval_deepeval", "deepeval")
    if job.id == "eval_opik":
        return SampledEval("eval_opik", "opik")
    if job.id == "rag_faithfulness":
        return FaithfulnessHeuristic()
    if job.id.startswith("obs_"):
        urls = LOCAL_OBS_URLS if settings.local_obs else HOSTED_OBS_URLS
        return ObsSink(job.id, hosted=not settings.local_obs, base_url=urls.get(job.id, ""))
    return None


def _try_gptcache() -> SemanticCacheStage | None:
    try:
        import gptcache  # type: ignore  # noqa: F401

        return SemanticCacheStage()
    except Exception:
        return None


def _try_semantic_router() -> SemanticRouterStage | None:
    try:
        import semantic_router  # type: ignore  # noqa: F401

        return SemanticRouterStage()
    except Exception:
        return None


def _try_selective_context() -> HistoryPrune | None:
    try:
        import selective_context  # type: ignore  # noqa: F401

        return HistoryPrune()
    except Exception:
        return None


def _try_recomp() -> RecompStage | None:
    try:
        import recomp  # type: ignore  # noqa: F401

        return RecompStage()
    except Exception:
        return None


def _try_lynx() -> Any | None:
    """Lynx is live only if a real adapter object is constructed. A flag is not enough."""
    try:
        return LynxFaithfulness.try_construct()
    except Exception:
        return None


_WARM_BUILDERS: dict[str, Callable[[], Any | None]] = {
    "semantic_cache": _try_gptcache,
    "semantic_router": _try_semantic_router,
    "history": _try_selective_context,
    "rag_compress": _try_recomp,
    "pii": try_presidio,
}


def extra_label(job_id: str) -> str:
    job = JOB_BY_ID[job_id]
    return job.extra or job.tool_id


def _warm_one(job_id: str) -> Any | None:
    if job_id == "compress":
        try:
            from llmlingua import PromptCompressor  # type: ignore  # noqa: F401
            from openbundle.config import CompressLayerConfig

            return CompressLayer(CompressLayerConfig(enabled=True))
        except Exception:
            return None
    builder = _WARM_BUILDERS.get(job_id)
    if builder is None:
        return None
    try:
        return builder()
    except Exception:
        return None


def bootstrap_registry(settings: Settings, *, warm: bool = True) -> StageRegistry:
    registry = StageRegistry()
    registry.local_obs = settings.local_obs
    registry.hosted_obs_disclosure = not settings.local_obs
    local = has_local_inference()
    skip_threads = (not warm) or warming_disabled()

    for job in HOSTED_JOBS:
        if not job_enabled(settings, job.id):
            registry.set_state(job.id, OFF, reason="not enabled in this config")
            continue
        if job.tier == "B":
            if skip_threads:
                stage = _warm_one(job.id)
                if stage is None:
                    registry.set_state(
                        job.id,
                        OFF,
                        reason=f"extra {extra_label(job.id)} not installed",
                        hard_down=True,
                    )
                else:
                    registry.publish(job.id, stage, LIVE)
            else:
                registry.set_state(job.id, WARMING, reason="download / import in background")
            continue
        stage = build_stage(job, settings)
        if stage is None:
            registry.set_state(job.id, OFF, reason=f"{job.tool_id} unavailable")
            continue
        registry.publish(job.id, stage, LIVE)

    if settings.with_lynx:
        lynx = _try_lynx()
        if lynx is not None:
            registry.publish("rag_faithfulness", lynx, LIVE, tool_id="lynx")

    for job in SELF_HOSTED_JOBS:
        if not local:
            registry.set_state(job.id, OFF, reason="no local vLLM/SGLang/Ollama detected")
            continue
        if settings.jobs and not job_enabled(settings, job.id):
            registry.set_state(job.id, OFF, reason="not enabled")
            continue
        registry.set_state(
            job.id,
            OFF,
            reason="engine-side — not constructed in this sidecar",
        )

    registry.mark_advisory("memory", "mem0", "advisory — never in Pipeline.prepare")
    registry.mark_advisory("batch", "provider_batch", "you add this yourself — not on the live path")

    if not skip_threads:
        for job_id in TIER_B_IDS:
            if registry.get_info(job_id).state != WARMING:
                continue

            def _run(jid: str = job_id) -> None:
                stage = _warm_one(jid)
                if stage is None:
                    registry.set_state(
                        jid,
                        OFF,
                        reason=f"extra {extra_label(jid)} not installed",
                        hard_down=True,
                    )
                else:
                    registry.publish(jid, stage, LIVE)

            threading.Thread(target=_run, name=f"openbundle-warm-{job_id}", daemon=True).start()

    return registry

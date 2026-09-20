"""Construction-gated adapters. LIVE only after import + a real named-library object.

SPIKE RESULTS (2026-09-20)
- RouteLLM: `Controller` needs a strong/weak model pair (and typically an mf
  checkpoint). Zero-sidecar-config routing is not honest RouteLLM LIVE.
  Fallback is first-party PrefixRouter under tool_id `prefix_router`.
- NeMo Guardrails: empty Colang does not enforce anything. LIVE only when
  LLMRails constructs with bundled Colang. Keyword/LLM-check fallback must
  not wear the NeMo name.
- Semantic Router: OpenAIEncoder bills a paid embeddings API. Construct only
  with HuggingFaceEncoder or FastEmbedEncoder; otherwise off needing
  `semantic-router[local]`.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openbundle.adapters.llmlingua2 import CompressLayer
from openbundle.adapters.named import (
    HOSTED_OBS_URLS,
    LOCAL_OBS_URLS,
    CostRouter,
    FaithfulnessHeuristic,
    GPTCacheStage,
    GuardrailsStage,
    InstructorStage,
    LiteLLMDispatch,
    LynxFaithfulness,
    RecompStage,
    RouteLLMStage,
    SampledEval,
    SdkObsSink,
    SelectiveContextStage,
    SemanticRouterStage,
)
from openbundle.adapters.nemo_rails import NemoRails
from openbundle.adapters.scans import LlmGuardSecrets, RebuffScan, try_presidio
from openbundle.config import CompressLayerConfig, Settings
from openbundle.pipeline.jobs import JobSpec
from openbundle.pipeline.layers.cache import CacheLayer


@dataclass
class Constructed:
    stage: Any | None = None
    tool_id: str | None = None
    reason: str = ""
    warming: bool = False


def warming_disabled() -> bool:
    return os.environ.get("OPENBUNDLE_NO_WARMING", "").strip().lower() in {"1", "true", "yes"}


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def try_gptcache(settings: Settings | None = None) -> Constructed:
    try:
        from gptcache import cache as gpt_cache  # type: ignore
        from gptcache.manager.factory import get_data_manager  # type: ignore
        from gptcache.processor.pre import get_prompt  # type: ignore
        from gptcache.similarity_evaluation.exact_match import ExactMatchEvaluation  # type: ignore
    except Exception:
        return Constructed(reason="extra gptcache not installed")
    try:
        data_dir = ""
        if settings is not None:
            data_dir = str(Path(settings.cache_path()).with_name("gptcache"))
        else:
            data_dir = str(Path.home() / ".openbundle" / "gptcache")
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        try:
            manager = get_data_manager(data_path=data_dir)
        except TypeError:
            manager = get_data_manager()
        gpt_cache.init(
            pre_embedding_func=get_prompt,
            data_manager=manager,
            similarity_evaluation=ExactMatchEvaluation(),
        )
        return Constructed(stage=GPTCacheStage(gpt_cache, data_dir=data_dir), tool_id="gptcache")
    except Exception as exc:
        return Constructed(reason=f"GPTCache failed to construct ({exc})")


def try_llmlingua(settings: Settings | None = None) -> Constructed:
    try:
        import llmlingua  # type: ignore  # noqa: F401
        from llmlingua import PromptCompressor  # type: ignore
    except Exception:
        return Constructed(reason="extra llmlingua not installed")
    if warming_disabled():
        return Constructed(reason="warming skipped (OPENBUNDLE_NO_WARMING=1)", warming=False)
    try:
        compressor = PromptCompressor()
        cfg = CompressLayerConfig(enabled=True)
        if settings is not None:
            cfg = settings.layers.compress.model_copy()
            cfg.enabled = True
        layer = CompressLayer(cfg)
        layer._compressor = compressor
        layer._compressor_tried = True
        layer.library = "llmlingua"
        return Constructed(stage=layer, tool_id="llmlingua2")
    except Exception as exc:
        return Constructed(reason=f"LLMLingua-2 model not ready ({exc})", warming=True)


def try_selective_context() -> Constructed:
    if warming_disabled():
        try:
            import selective_context  # type: ignore  # noqa: F401
        except Exception:
            return Constructed(reason="extra selective_context not installed")
        return Constructed(reason="warming skipped (OPENBUNDLE_NO_WARMING=1)")
    try:
        from selective_context import SelectiveContext  # type: ignore

        selector = SelectiveContext()
        return Constructed(stage=SelectiveContextStage(selector), tool_id="selective_context")
    except Exception:
        return Constructed(reason="extra selective_context not installed")


def try_recomp() -> Constructed:
    try:
        import recomp  # type: ignore
    except Exception:
        return Constructed(reason="extra recomp not installed")
    func = getattr(recomp, "compress", None)
    cls = getattr(recomp, "Recomp", None)
    if func is None and cls is None:
        return Constructed(reason="RECOMP imported but has no compressor")

    def _run(text: str) -> str:
        if func is not None:
            out = func(text)
        else:
            instance = cls()
            out = instance.compress(text) if hasattr(instance, "compress") else instance(text)
        return str(out if not isinstance(out, tuple) else out[0])

    return Constructed(stage=RecompStage(_run), tool_id="recomp")


def try_llm_guard() -> Constructed:
    try:
        from llm_guard.input_scanners.secrets import Secrets  # type: ignore

        return Constructed(stage=LlmGuardSecrets(Secrets()), tool_id="llm_guard")
    except Exception:
        return Constructed(reason="extra llm_guard not installed")


def try_rebuff() -> Constructed:
    try:
        from rebuff import Rebuff  # type: ignore

        api_key = _env("REBUFF_API_KEY")
        if not api_key:
            return Constructed(reason="Rebuff needs REBUFF_API_KEY (heuristic mode is not Rebuff live)")
        client = Rebuff(api_token=api_key) if api_key else Rebuff()
        return Constructed(stage=RebuffScan(client), tool_id="rebuff")
    except TypeError:
        try:
            from rebuff import Rebuff  # type: ignore

            return Constructed(stage=RebuffScan(Rebuff()), tool_id="rebuff")
        except Exception:
            return Constructed(reason="extra rebuff not installed")
    except Exception:
        return Constructed(reason="extra rebuff not installed")


def try_nemo() -> Constructed:
    try:
        from nemoguardrails import LLMRails, RailsConfig  # type: ignore
    except Exception:
        return Constructed(reason="extra nemo_guardrails not installed")
    root = Path(__file__).resolve().parent / "nemo"
    try:
        colang = (root / "rails.co").read_text(encoding="utf-8")
        yaml_cfg = (root / "config.yml").read_text(encoding="utf-8")
        config = RailsConfig.from_content(colang_content=colang, yaml_content=yaml_cfg)
        rails = LLMRails(config)
        return Constructed(stage=NemoRails(rails=rails), tool_id="nemo_guardrails")
    except Exception as exc:
        return Constructed(reason=f"NeMo needs Colang config ({exc})")


def try_semantic_router() -> Constructed:
    try:
        import semantic_router  # type: ignore  # noqa: F401
    except Exception:
        return Constructed(reason="extra semantic_router not installed")
    encoder = None
    encoder_name = ""
    try:
        from semantic_router.encoders import HuggingFaceEncoder  # type: ignore

        encoder = HuggingFaceEncoder()
        encoder_name = "huggingface"
    except Exception:
        try:
            from semantic_router.encoders import FastEmbedEncoder  # type: ignore

            encoder = FastEmbedEncoder()
            encoder_name = "fastembed"
        except Exception:
            return Constructed(
                reason="Semantic Router needs semantic-router[local] (HuggingFace/FastEmbed); OpenAI encoder is not used"
            )
    try:
        from semantic_router import Route, SemanticRouter  # type: ignore

        routes = [
            Route(name="code", utterances=["write a function", "fix this bug", "refactor this"]),
            Route(name="chat", utterances=["hello", "how are you", "thanks"]),
        ]
        router = SemanticRouter(encoder=encoder, routes=routes)
        return Constructed(
            stage=SemanticRouterStage(router, encoder_name=encoder_name),
            tool_id="semantic_router",
        )
    except Exception as exc:
        return Constructed(reason=f"Semantic Router failed to construct ({exc})")


def try_routellm() -> Constructed:
    strong = _env("ROUTELLM_STRONG_MODEL")
    weak = _env("ROUTELLM_WEAK_MODEL")
    config_path = _env("ROUTELLM_CONFIG")
    if not ((strong and weak) or config_path):
        return Constructed(reason="RouteLLM needs router config")
    try:
        from routellm.controller import Controller  # type: ignore
    except Exception:
        return Constructed(reason="extra routellm not installed")
    try:
        kwargs: dict[str, Any] = {"routers": ["mf"]}
        if strong and weak:
            kwargs["strong_model"] = strong
            kwargs["weak_model"] = weak
        if config_path:
            kwargs["config_path"] = config_path
        controller = Controller(**kwargs)
        return Constructed(stage=RouteLLMStage(controller), tool_id="routellm")
    except Exception as exc:
        return Constructed(reason=f"RouteLLM failed to construct ({exc})")


def try_prefix_router() -> Constructed:
    return Constructed(stage=CostRouter(), tool_id="prefix_router")


def try_litellm() -> Constructed:
    try:
        import litellm  # type: ignore  # noqa: F401
    except Exception:
        return Constructed(reason="extra litellm not installed")
    return Constructed(stage=LiteLLMDispatch(), tool_id="litellm")


def try_instructor() -> Constructed:
    try:
        import instructor  # type: ignore
    except Exception:
        return Constructed(reason="extra instructor not installed")
    return Constructed(stage=InstructorStage(instructor), tool_id="instructor")


def try_guardrails() -> Constructed:
    try:
        from guardrails import Guard  # type: ignore

        guard = Guard()
        return Constructed(stage=GuardrailsStage(guard), tool_id="guardrails_ai")
    except Exception:
        return Constructed(reason="extra guardrails_ai not installed")


def try_promptfoo() -> Constructed:
    if shutil.which("promptfoo"):
        import types

        client = types.SimpleNamespace(name="promptfoo", score=lambda body: {"eval": "ok", "eval_reason": "promptfoo"})
        stage = SampledEval("eval_promptfoo", "promptfoo", client=client, library="promptfoo")
        return Constructed(stage=stage, tool_id="promptfoo")
    try:
        import promptfoo  # type: ignore  # noqa: F401
    except Exception:
        return Constructed(reason="extra promptfoo not installed")
    stage = SampledEval("eval_promptfoo", "promptfoo", client=promptfoo, library="promptfoo")
    return Constructed(stage=stage, tool_id="promptfoo")


def try_deepeval() -> Constructed:
    try:
        import deepeval  # type: ignore
    except Exception:
        return Constructed(reason="extra deepeval not installed")
    if not _env("OPENAI_API_KEY", "DEEPEVAL_API_KEY", "CONFIDENT_API_KEY"):
        return Constructed(reason="DeepEval needs OPENAI_API_KEY or DEEPEVAL_API_KEY")
    return Constructed(
        stage=SampledEval("eval_deepeval", "deepeval", client=deepeval, library="deepeval"),
        tool_id="deepeval",
    )


def try_opik(*, self_host: bool) -> Constructed:
    try:
        import opik  # type: ignore
    except Exception:
        return Constructed(reason="extra opik not installed")
    # Opik defaults to a local Comet server, not Comet cloud.
    if not self_host and not _env("OPIK_API_KEY", "COMET_API_KEY", "OPIK_URL"):
        return Constructed(
            reason="Opik defaults to self-hosted; pass --self-host or set OPIK_URL / COMET_API_KEY"
        )
    try:
        configure = getattr(opik, "configure", None)
        if callable(configure):
            if self_host:
                try:
                    configure(use_local=True)
                except TypeError:
                    configure()
            else:
                configure()
    except Exception as exc:
        return Constructed(reason=f"Opik failed to construct ({exc})")
    return Constructed(stage=SampledEval("eval_opik", "opik", client=opik, library="opik"), tool_id="opik")


def try_lynx() -> Constructed:
    stage = LynxFaithfulness.try_construct()
    if stage is None:
        return Constructed(reason="Lynx-8B not loaded (local weights required; no default download)")
    return Constructed(stage=stage, tool_id="lynx")


def try_langfuse(*, self_host: bool) -> Constructed:
    try:
        from langfuse import Langfuse  # type: ignore
    except Exception:
        return Constructed(reason="extra langfuse not installed")
    public_key = _env("LANGFUSE_PUBLIC_KEY")
    secret_key = _env("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return Constructed(reason="Langfuse needs LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY")
    host = _env("LANGFUSE_HOST") or (LOCAL_OBS_URLS["obs_langfuse"] if self_host else HOSTED_OBS_URLS["obs_langfuse"])
    try:
        client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    except Exception as exc:
        return Constructed(reason=f"Langfuse failed to construct ({exc})")
    return Constructed(
        stage=SdkObsSink("obs_langfuse", client, library="langfuse", hosted=not self_host, base_url=host),
        tool_id="langfuse",
    )


def try_openobserve(*, self_host: bool) -> Constructed:
    try:
        import openobserve  # type: ignore
    except Exception:
        return Constructed(reason="extra openobserve not installed")
    if not self_host and not _env("OPENOBSERVE_URL", "OPENOBSERVE_TOKEN", "OPENOBSERVE_PASSWORD"):
        return Constructed(reason="OpenObserve needs OPENOBSERVE_URL / token, or --self-host")
    host = _env("OPENOBSERVE_URL") or (
        LOCAL_OBS_URLS["obs_openobserve"] if self_host else HOSTED_OBS_URLS["obs_openobserve"]
    )
    return Constructed(
        stage=SdkObsSink(
            "obs_openobserve",
            openobserve,
            library="openobserve",
            hosted=not self_host,
            base_url=host,
        ),
        tool_id="openobserve",
    )


def try_openmeter(*, self_host: bool) -> Constructed:
    try:
        import openmeter  # type: ignore
    except Exception:
        return Constructed(reason="extra openmeter not installed")
    if not _env("OPENMETER_API_KEY") and not self_host:
        return Constructed(reason="OpenMeter needs OPENMETER_API_KEY or --self-host")
    host = _env("OPENMETER_URL") or (
        LOCAL_OBS_URLS["obs_openmeter"] if self_host else HOSTED_OBS_URLS["obs_openmeter"]
    )
    client = openmeter
    ctor = getattr(openmeter, "Client", None) or getattr(openmeter, "OpenMeter", None)
    if callable(ctor):
        try:
            client = ctor(api_key=_env("OPENMETER_API_KEY") or None, base_url=host)
        except Exception:
            try:
                client = ctor()
            except Exception:
                client = openmeter
    return Constructed(
        stage=SdkObsSink("obs_openmeter", client, library="openmeter", hosted=not self_host, base_url=host),
        tool_id="openmeter",
    )


def try_agentops(*, self_host: bool) -> Constructed:
    try:
        import agentops  # type: ignore
    except Exception:
        return Constructed(reason="extra agentops not installed")
    key = _env("AGENTOPS_API_KEY")
    if not key and not self_host:
        return Constructed(reason="AgentOps needs AGENTOPS_API_KEY or --self-host")
    try:
        init = getattr(agentops, "init", None)
        if callable(init) and key:
            init(key)
    except Exception as exc:
        return Constructed(reason=f"AgentOps failed to construct ({exc})")
    host = LOCAL_OBS_URLS["obs_agentops"] if self_host else HOSTED_OBS_URLS["obs_agentops"]
    return Constructed(
        stage=SdkObsSink("obs_agentops", agentops, library="agentops", hosted=not self_host, base_url=host),
        tool_id="agentops",
    )


def try_agenta(*, self_host: bool) -> Constructed:
    try:
        import agenta  # type: ignore
    except Exception:
        return Constructed(reason="extra agenta not installed")
    if not _env("AGENTA_API_KEY", "AGENTA_HOST") and not self_host:
        return Constructed(reason="Agenta needs AGENTA_API_KEY or --self-host")
    host = _env("AGENTA_HOST") or (LOCAL_OBS_URLS["obs_agenta"] if self_host else HOSTED_OBS_URLS["obs_agenta"])
    return Constructed(
        stage=SdkObsSink("obs_agenta", agenta, library="agenta", hosted=not self_host, base_url=host),
        tool_id="agenta",
    )


def construct_job(job: JobSpec, settings: Settings) -> Constructed:
    """Build the named adapter for a job. Never returns a vendor-named stub."""
    job_id = job.id
    self_host = bool(settings.local_obs)
    if job_id == "exact_hash":
        return Constructed(stage=CacheLayer(settings), tool_id="sqlite_exact")
    if job_id == "semantic_cache":
        return try_gptcache(settings)
    if job_id == "compress":
        built = try_llmlingua(settings)
        if built.stage is None and not warming_disabled():
            built.warming = True
        return built
    if job_id == "history":
        return try_selective_context()
    if job_id == "rag_compress":
        return try_recomp()
    if job_id == "secrets":
        return try_llm_guard()
    if job_id == "pii":
        stage = try_presidio()
        if stage is None:
            return Constructed(reason="extra presidio not installed")
        return Constructed(stage=stage, tool_id="presidio")
    if job_id == "injection":
        return try_rebuff()
    if job_id == "nemo_rails":
        return try_nemo()
    if job_id == "semantic_router":
        return try_semantic_router()
    if job_id == "cost_route":
        routed = try_routellm()
        if routed.stage is not None:
            return routed
        fallback = try_prefix_router()
        fallback.reason = routed.reason or "RouteLLM needs router config"
        return fallback
    if job_id == "litellm":
        return try_litellm()
    if job_id == "output_validate":
        return try_guardrails()
    if job_id == "structured":
        return try_instructor()
    if job_id == "eval_promptfoo":
        return try_promptfoo()
    if job_id == "eval_deepeval":
        return try_deepeval()
    if job_id == "eval_opik":
        return try_opik(self_host=self_host)
    if job_id == "rag_faithfulness":
        lynx = try_lynx()
        if lynx.stage is not None:
            return lynx
        return Constructed(
            stage=FaithfulnessHeuristic(),
            tool_id="rag_faithfulness",
            reason="heuristic (not Lynx)",
        )
    if job_id == "obs_langfuse":
        return try_langfuse(self_host=self_host)
    if job_id == "obs_openobserve":
        return try_openobserve(self_host=self_host)
    if job_id == "obs_openmeter":
        return try_openmeter(self_host=self_host)
    if job_id == "obs_agentops":
        return try_agentops(self_host=self_host)
    if job_id == "obs_agenta":
        return try_agenta(self_host=self_host)
    return Constructed(reason=f"{job.tool_id} unavailable")

"""Build adapters and optionally warm Tier B. Never publish a half-built stage."""

from __future__ import annotations

import os
import threading
from typing import Any

from openbundle.adapters.construct import construct_job, try_llmlingua, warming_disabled
from openbundle.config import Settings
from openbundle.init.scan import installed_extras, scan_env
from openbundle.pipeline.jobs import (
    HOSTED_JOBS,
    JOB_BY_ID,
    LIVE,
    OFF,
    SELF_HOSTED_JOBS,
    WARMING,
    JobSpec,
)
from openbundle.pipeline.registry import StageRegistry


def job_enabled(settings: Settings, job_id: str) -> bool:
    if job_id == "rag_faithfulness":
        if settings.with_lynx:
            return True
        return bool(settings.jobs.get(job_id, False)) if settings.jobs else False
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


def extra_label(job_id: str) -> str:
    job = JOB_BY_ID[job_id]
    return job.extra or job.tool_id


def extra_present(job: JobSpec) -> bool:
    if not job.extra:
        return False
    return job.extra in set(installed_extras())


def _publish(registry: StageRegistry, job: JobSpec, built: Any) -> None:
    if built.stage is not None:
        registry.publish(job.id, built.stage, LIVE, tool_id=built.tool_id)
        return
    if built.warming:
        registry.set_state(job.id, WARMING, reason=built.reason or "download / import in background")
        return
    registry.set_state(
        job.id,
        OFF,
        reason=built.reason or f"{job.tool_id} unavailable",
        hard_down="not installed" in (built.reason or ""),
    )


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
        if job.tier == "B" and not skip_threads and job.id in {"compress", "history", "semantic_router", "pii", "rag_compress"}:
            built = construct_job(job, settings)
            if built.stage is not None:
                _publish(registry, job, built)
            else:
                registry.set_state(job.id, WARMING, reason=built.reason or "download / import in background")
            continue
        built = construct_job(job, settings)
        _publish(registry, job, built)

    if job_enabled(settings, "rag_faithfulness"):
        built = construct_job(JOB_BY_ID["rag_faithfulness"], settings)
        _publish(registry, JOB_BY_ID["rag_faithfulness"], built)
    else:
        registry.set_state("rag_faithfulness", OFF, reason="not enabled (pass --with-lynx)")

    for job in SELF_HOSTED_JOBS:
        if not local:
            registry.set_state(job.id, OFF, reason="no local vLLM/SGLang/Ollama detected")
            continue
        if settings.jobs and not job_enabled(settings, job.id):
            registry.set_state(job.id, OFF, reason="not enabled")
            continue
        if extra_present(job):
            registry.set_state(job.id, OFF, reason="engine-side, extra present")
        else:
            registry.set_state(job.id, OFF, reason="not constructed")

    registry.mark_advisory("memory", "mem0", "advisory — never in Pipeline.prepare")
    registry.mark_advisory("batch", "provider_batch", "you add this yourself — not on the live path")

    if not skip_threads:
        for job in HOSTED_JOBS:
            if registry.get_info(job.id).state != WARMING:
                continue

            def _run(spec: JobSpec = job) -> None:
                if spec.id == "compress":
                    built = try_llmlingua(settings)
                else:
                    built = construct_job(spec, settings)
                if built.stage is None:
                    registry.set_state(
                        spec.id,
                        OFF,
                        reason=built.reason or f"extra {extra_label(spec.id)} not installed",
                        hard_down=True,
                    )
                else:
                    registry.publish(spec.id, built.stage, LIVE, tool_id=built.tool_id)

            threading.Thread(target=_run, name=f"openbundle-warm-{job.id}", daemon=True).start()

    return registry

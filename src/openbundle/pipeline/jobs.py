"""27 jobs: 23 hosted-API + 4 self-hosted. One named tool per job."""

from __future__ import annotations

from dataclasses import dataclass

LIVE = "live"
WARMING = "warming"
DEGRADED = "degraded"
ADVISORY = "advisory"
OFF = "off"

STATES = (LIVE, WARMING, DEGRADED, ADVISORY, OFF)


@dataclass(frozen=True)
class JobSpec:
    id: str
    tool_id: str
    label: str
    tier: str  # A | B | C | self_hosted
    extra: str | None = None
    path: str = "prepare"  # prepare | after | obs
    scan: bool = False


# Pipeline order (hard-coded). Cache keys original messages; compress on miss only.
HOSTED_JOBS: tuple[JobSpec, ...] = (
    JobSpec("exact_hash", "sqlite_exact", "exact-hash cache", "A"),
    JobSpec("semantic_cache", "gptcache", "semantic cache", "B", extra="gptcache"),
    JobSpec("compress", "llmlingua2", "compress", "B", extra="llmlingua"),
    JobSpec("history", "selective_context", "history prune", "B", extra="selective_context"),
    JobSpec("rag_compress", "recomp", "RAG compress", "B", extra="recomp"),
    JobSpec("secrets", "llm_guard", "secrets scan", "A", scan=True),
    JobSpec("pii", "presidio", "PII scan", "B", extra="presidio", scan=True),
    JobSpec("injection", "rebuff", "injection scan", "A", scan=True),
    JobSpec("nemo_rails", "nemo_guardrails", "NeMo rails", "A"),
    JobSpec("semantic_router", "semantic_router", "semantic router", "B", extra="semantic_router"),
    JobSpec("cost_route", "routellm", "cost router", "A"),
    JobSpec("litellm", "litellm", "LiteLLM dispatch", "A"),
    JobSpec("output_validate", "guardrails_ai", "output validate", "A", path="after"),
    JobSpec("structured", "instructor", "structured output", "A", path="after"),
    JobSpec("eval_promptfoo", "promptfoo", "promptfoo", "A", path="after"),
    JobSpec("eval_deepeval", "deepeval", "DeepEval", "A", path="after"),
    JobSpec("eval_opik", "opik", "Opik", "A", path="after"),
    JobSpec("rag_faithfulness", "rag_faithfulness", "RAG faithfulness", "A", path="after"),
    JobSpec("obs_langfuse", "langfuse", "Langfuse", "C", path="obs"),
    JobSpec("obs_openobserve", "openobserve", "OpenObserve", "C", path="obs"),
    JobSpec("obs_openmeter", "openmeter", "OpenMeter", "A", path="obs"),
    JobSpec("obs_agentops", "agentops", "AgentOps", "A", path="obs"),
    JobSpec("obs_agenta", "agenta", "Agenta", "C", path="obs"),
)

SELF_HOSTED_JOBS: tuple[JobSpec, ...] = (
    JobSpec("lmcache", "lmcache", "LMCache", "self_hosted", extra="lmcache"),
    JobSpec("kvcached", "kvcached", "kvcached", "self_hosted", extra="kvcached"),
    JobSpec("kvzip", "kvzip", "KVzip", "self_hosted", extra="kvzip"),
    JobSpec("deepspec", "deepspec", "DeepSpec", "self_hosted", extra="deepspec"),
)

ALL_JOBS: tuple[JobSpec, ...] = HOSTED_JOBS + SELF_HOSTED_JOBS
JOB_BY_ID: dict[str, JobSpec] = {job.id: job for job in ALL_JOBS}
HOSTED_JOB_IDS: tuple[str, ...] = tuple(job.id for job in HOSTED_JOBS)
SELF_HOSTED_JOB_IDS: tuple[str, ...] = tuple(job.id for job in SELF_HOSTED_JOBS)
TIER_A_IDS: tuple[str, ...] = tuple(job.id for job in HOSTED_JOBS if job.tier in {"A", "C"})
TIER_B_IDS: tuple[str, ...] = tuple(job.id for job in HOSTED_JOBS if job.tier == "B")
SCAN_JOB_IDS: tuple[str, ...] = tuple(job.id for job in ALL_JOBS if job.scan)
PREPARE_JOB_IDS: tuple[str, ...] = tuple(job.id for job in HOSTED_JOBS if job.path == "prepare")
AFTER_JOB_IDS: tuple[str, ...] = tuple(job.id for job in HOSTED_JOBS if job.path in {"after", "obs"})

HOSTED_JOB_COUNT = len(HOSTED_JOBS)
SELF_HOSTED_JOB_COUNT = len(SELF_HOSTED_JOBS)

# Catalog / CLI still talk in wrap categories for a few leftover UIs.
WRAP_JOBS = HOSTED_JOB_IDS
ADVISORY_CATEGORIES = ("memory", "batch")
ALL_PICK_CATEGORIES = HOSTED_JOB_IDS + ADVISORY_CATEGORIES

LAYER_DEFAULT_TOOL = {job.id: job.tool_id for job in ALL_JOBS}
LAYER_DEFAULT_TOOL["memory"] = "none"
LAYER_DEFAULT_TOOL["batch"] = "none"

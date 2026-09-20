"""Pick one tool per job. Memory and batch stay advisory."""

from __future__ import annotations

from dataclasses import dataclass, field

from openbundle.init.scan import ScanResult, installed_extras
from openbundle.kb.catalog import (
    ADVISORY_CATEGORIES,
    Tool,
    get_tool,
    incompatibility,
    tools_in_category,
)
from openbundle.pipeline.bootstrap import has_local_inference
from openbundle.pipeline.jobs import HOSTED_JOB_IDS, LAYER_DEFAULT_TOOL, SELF_HOSTED_JOB_IDS


@dataclass
class CategoryChoice:
    category: str
    tool_id: str
    live: bool = False
    reasons: dict[str, str] = field(default_factory=dict)

    @property
    def skipped(self) -> bool:
        return self.tool_id in {"", "none"}


@dataclass
class Selection:
    jobs: dict[str, str]
    profile: str
    extras: list[str]
    details: dict[str, CategoryChoice] = field(default_factory=dict)
    live: dict[str, bool] = field(default_factory=dict)
    local_inference: bool = False
    with_lynx: bool = False
    local_obs: bool = False
    openrouter: bool = False

    def __getattr__(self, name: str) -> str:
        if name in self.jobs:
            return self.jobs[name]
        raise AttributeError(name)

    @property
    def cache(self) -> str:
        return self.jobs.get("exact_hash", "sqlite_exact")

    @property
    def compress(self) -> str:
        return self.jobs.get("compress", "none")

    @property
    def memory(self) -> str:
        return "none"

    @property
    def routing(self) -> str:
        return self.jobs.get("cost_route", "none")

    @property
    def guardrails(self) -> str:
        return self.jobs.get("secrets", "none")

    @property
    def structured(self) -> str:
        return self.jobs.get("structured", "none")

    @property
    def eval(self) -> str:
        return self.jobs.get("eval_promptfoo", "none")

    @property
    def coalesce(self) -> str:
        return "none"

    @property
    def prompt_cache(self) -> str:
        return "none"

    @property
    def context(self) -> str:
        return "none"

    @property
    def batch(self) -> str:
        return "none"


def select(
    scan: ScanResult,
    extras: list[str] | None = None,
    *,
    approved_extras: bool | None = None,
    core_only: bool = False,
    allow_lossy: bool = True,
    with_lynx: bool = False,
    local_obs: bool = False,
) -> Selection:
    if approved_extras is False:
        core_only = True
    found = extras if extras is not None else installed_extras()
    extra_set = set() if core_only else set(found)
    profile = "coding-agent" if scan.coding_agent else "api-app"
    local = has_local_inference(scan)
    chosen: list[str] = []
    details: dict[str, CategoryChoice] = {}
    jobs: dict[str, str] = {}
    live: dict[str, bool] = {}

    for job_id in HOSTED_JOB_IDS:
        default = LAYER_DEFAULT_TOOL[job_id]
        if core_only and job_id != "exact_hash":
            choice = CategoryChoice(job_id, "none", live=False, reasons={default: "skipped (--core-only)"})
            details[job_id] = choice
            jobs[job_id] = "none"
            live[job_id] = False
            continue
        tool = get_tool(default)
        why = incompatibility(tool, extra_set, chosen, core_only=core_only) if tool else "not in catalog"
        # Tier A/C first-party jobs stay selected even when an extra is missing.
        # Tier B stays selected in yaml; runtime marks warming/off.
        selected = default if tool and tool.status == "active" else "none"
        is_live = selected != "none" and (tool.tier in {"A", "C"} if tool else False)
        if tool and tool.tier == "B":
            is_live = False
        reasons = {}
        if tool:
            for other in tools_in_category(job_id):
                skip = incompatibility(other, extra_set, chosen + [selected], core_only=core_only)
                if skip:
                    reasons[other.id] = skip
        choice = CategoryChoice(job_id, selected, live=is_live, reasons=reasons)
        details[job_id] = choice
        jobs[job_id] = selected
        live[job_id] = is_live
        if selected != "none":
            chosen.append(selected)

    for job_id in SELF_HOSTED_JOB_IDS:
        default = LAYER_DEFAULT_TOOL[job_id]
        if not local:
            details[job_id] = CategoryChoice(
                job_id, "none", live=False, reasons={default: "no local vLLM/SGLang/Ollama detected"}
            )
            jobs[job_id] = "none"
            live[job_id] = False
            continue
        details[job_id] = CategoryChoice(
            job_id,
            default,
            live=False,
            reasons={default: "engine-side — not constructed in this sidecar"},
        )
        jobs[job_id] = default
        live[job_id] = False

    if with_lynx:
        jobs["rag_faithfulness"] = "lynx"
        live["rag_faithfulness"] = False
        details["rag_faithfulness"] = CategoryChoice(
            "rag_faithfulness",
            "lynx",
            live=False,
            reasons={"lynx": "conditional — live only if Lynx-8B constructs"},
        )
    else:
        jobs["rag_faithfulness"] = "none"
        live["rag_faithfulness"] = False

    for category in ADVISORY_CATEGORIES:
        reasons = {tool.id: "you add this yourself — not on the live path" for tool in tools_in_category(category)}
        details[category] = CategoryChoice(category, "none", live=False, reasons=reasons)
        jobs[category] = "none"
        live[category] = False

    return Selection(
        jobs=jobs,
        profile=profile,
        extras=list(found),
        details=details,
        live=live,
        local_inference=local,
        with_lynx=with_lynx and (local or with_lynx),
        local_obs=local_obs,
        openrouter=bool(scan.openrouter_key),
    )


def explain_category(
    category: str,
    extras: list[str] | None = None,
    *,
    chosen: list[str] | None = None,
    core_only: bool = False,
) -> list[tuple[Tool, str | None]]:
    extra_set = set() if core_only else set(extras if extras is not None else installed_extras())
    taken = list(chosen or [])
    rows: list[tuple[Tool, str | None]] = []
    for tool in tools_in_category(category):
        if category in ADVISORY_CATEGORIES or tool.lane == "advisory":
            rows.append((tool, "you add this yourself — not on the live path"))
            continue
        rows.append((tool, incompatibility(tool, extra_set, taken, core_only=core_only)))
    return rows

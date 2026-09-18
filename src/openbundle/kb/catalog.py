"""Load catalog.yaml. credit_line is the only user-facing wording for a tool."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from openbundle.pipeline.jobs import (
    ADVISORY_CATEGORIES,
    HOSTED_JOB_COUNT,
    LAYER_DEFAULT_TOOL,
    SELF_HOSTED_JOB_COUNT,
    WRAP_JOBS,
)

WRAP_CATEGORIES = WRAP_JOBS
INIT_SKIP_GENERIC = "no compatible tool for this setup"

CATALOG_CATEGORY = {
    "exact_hash": "caching",
    "semantic_cache": "caching",
    "compress": "prompt_compression",
    "history": "prompt_compression",
    "rag_compress": "prompt_compression",
    "secrets": "guardrails",
    "pii": "guardrails",
    "injection": "guardrails",
    "nemo_rails": "guardrails",
    "semantic_router": "routing",
    "cost_route": "routing",
    "litellm": "routing",
    "output_validate": "guardrails",
    "structured": "structured_output",
    "eval_promptfoo": "evaluation",
    "eval_deepeval": "evaluation",
    "eval_opik": "evaluation",
    "rag_faithfulness": "evaluation",
    "obs_langfuse": "observability",
    "obs_openobserve": "observability",
    "obs_openmeter": "observability",
    "obs_agentops": "observability",
    "obs_agenta": "observability",
    "lmcache": "caching",
    "kvcached": "caching",
    "kvzip": "caching",
    "deepspec": "speculative_decoding",
    "memory": "agent_memory",
    "batch": "batch",
}


@dataclass(frozen=True)
class Tool:
    id: str
    name: str
    categories: list[str]
    license: str = ""
    how_open: str = ""
    status: str = "mapped"
    extra: str | None = None
    adapter: str = ""
    url: str = ""
    credit_line: str = ""
    notes: str = ""
    lane: str = "catalog_only"
    job: str = ""
    tier: str = ""
    role: str = ""

    def credited(self) -> str:
        return self.credit_line or self.name


def _kb_path(name: str) -> Path:
    return Path(__file__).resolve().parent / name


@lru_cache(maxsize=1)
def _catalog_data() -> dict[str, Any]:
    with _kb_path("catalog.yaml").open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("catalog.yaml must be a mapping")
    return data


@lru_cache(maxsize=1)
def _profiles_data() -> dict[str, Any]:
    with _kb_path("profiles.yaml").open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("profiles.yaml must be a mapping")
    return data


@lru_cache(maxsize=1)
def _compat_data() -> dict[str, Any]:
    with _kb_path("compat.yaml").open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("compat.yaml must be a mapping")
    return data


def load_tools() -> list[Tool]:
    rows: list[Tool] = []
    for raw in _catalog_data().get("tools") or []:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        extra = raw.get("extra")
        rows.append(
            Tool(
                id=str(raw["id"]),
                name=str(raw.get("name") or raw["id"]),
                categories=[str(c) for c in (raw.get("categories") or [])],
                license=str(raw.get("license") or ""),
                how_open=str(raw.get("how_open") or ""),
                status=str(raw.get("status") or "mapped"),
                extra=None if extra in (None, "", "null") else str(extra),
                adapter=str(raw.get("adapter") or ""),
                url=str(raw.get("url") or ""),
                credit_line=str(raw.get("credit_line") or raw.get("name") or raw["id"]),
                notes=str(raw.get("notes") or ""),
                lane=str(raw.get("lane") or "catalog_only"),
                job=str(raw.get("job") or ""),
                tier=str(raw.get("tier") or ""),
                role=str(raw.get("role") or ""),
            )
        )
    return rows


def tools_by_id() -> dict[str, Tool]:
    return {tool.id: tool for tool in load_tools()}


def get_tool(tool_id: str) -> Tool | None:
    if not tool_id or tool_id == "none":
        return None
    return tools_by_id().get(tool_id)


def credit_line(tool_id: str) -> str:
    tool = get_tool(tool_id)
    return tool.credited() if tool else tool_id


def lane_counts() -> dict[str, int]:
    counts = {"wrap": 0, "advisory": 0, "catalog_only": 0}
    for tool in load_tools():
        lane = tool.lane if tool.lane in counts else "catalog_only"
        counts[lane] += 1
    return counts


def job_headline_counts() -> tuple[int, int, int]:
    """(hosted primaries, self-hosted primaries, advisory tools). Generated, never hand-typed."""
    hosted = 0
    self_hosted = 0
    advisory = 0
    for tool in load_tools():
        if tool.role == "primary" and tool.lane == "wrap" and tool.tier in {"A", "B", "C"}:
            hosted += 1
        elif tool.role == "primary" and tool.tier == "self_hosted":
            self_hosted += 1
        elif tool.lane == "advisory":
            advisory += 1
    if hosted != HOSTED_JOB_COUNT or self_hosted != SELF_HOSTED_JOB_COUNT:
        # still return actual catalog counts; tests lock equality with HOSTED_JOB_COUNT
        pass
    return hosted, self_hosted, advisory


def credit_for_layer(layer: str) -> str:
    if layer == "passthrough":
        return "passthrough"
    if layer == "cache":
        layer = "exact_hash"
    tool_id = LAYER_DEFAULT_TOOL.get(layer, layer)
    return credit_line(tool_id)


def candidates_for(category: str) -> list[str]:
    block = _profiles_data().get("candidates") or {}
    ordered = [str(item) for item in (block.get(category) or [])]
    if ordered:
        return ordered
    catalog_cat = CATALOG_CATEGORY.get(category, category)
    return [
        tool.id
        for tool in load_tools()
        if tool.job == category or catalog_cat in tool.categories
    ]


def tools_in_category(category: str) -> list[Tool]:
    ids = candidates_for(category)
    known = tools_by_id()
    extra = [
        tool
        for tool in load_tools()
        if (tool.job == category or CATALOG_CATEGORY.get(category, category) in tool.categories)
        and tool.id not in ids
    ]
    return [known[i] for i in ids if i in known] + extra


def conflict_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for row in _compat_data().get("conflicts") or []:
        if isinstance(row, list) and len(row) >= 2:
            pairs.append((str(row[0]), str(row[1])))
    return pairs


def conflicts_with(tool_id: str, chosen: list[str]) -> str | None:
    for left, right in conflict_pairs():
        if tool_id == left and right in chosen:
            return right
        if tool_id == right and left in chosen:
            return left
    return None


def incompatibility(
    tool: Tool,
    extras: set[str],
    chosen: list[str],
    *,
    core_only: bool = False,
) -> str | None:
    """Specific skip reason, or None if this tool can activate. Never INIT_SKIP_GENERIC."""
    if tool.lane == "catalog_only":
        return "not a live layer"
    if tool.lane == "advisory":
        return "you add this yourself — not on the live path"
    if tool.role == "alternate":
        return "same-job fallback — not the first pick"
    if tool.tier == "self_hosted":
        return "self-hosted inference only"
    if tool.status != "active":
        return "not wired"
    if tool.extra:
        if core_only:
            return f"extra {tool.extra} skipped (--core-only)"
        if tool.extra not in extras:
            return f"extra {tool.extra} not installed"
    other = conflicts_with(tool.id, chosen)
    if other:
        return f"conflicts with {other}"
    return None

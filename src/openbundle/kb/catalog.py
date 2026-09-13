"""Load catalog.yaml. credit_line is the only user-facing wording for a tool."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

WRAP_CATEGORIES = (
    "cache",
    "coalesce",
    "memory",
    "context",
    "compress",
    "prompt_cache",
    "routing",
    "guardrails",
    "structured",
    "eval",
)
ADVISORY_CATEGORIES = ("batch",)
ALL_PICK_CATEGORIES = WRAP_CATEGORIES + ADVISORY_CATEGORIES
CATALOG_CATEGORY = {
    "cache": "caching",
    "coalesce": "coalesce",
    "memory": "agent_memory",
    "context": "context_management",
    "compress": "prompt_compression",
    "prompt_cache": "prompt_caching",
    "routing": "routing",
    "guardrails": "guardrails",
    "structured": "structured_output",
    "eval": "evaluation",
    "batch": "batch",
}
LAYER_DEFAULT_TOOL = {
    "cache": "sqlite_exact",
    "coalesce": "singleflight",
    "memory": "summary",
    "context": "session_hygiene",
    "compress": "llmlingua2",
    "prompt_cache": "prompt_cache",
    "routing": "prefix_router",
    "guardrails": "input_guard",
    "structured": "json_schema",
    "eval": "sample_eval",
    "batch": "none",
}
INIT_SKIP_GENERIC = "no compatible tool for this setup"


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


def credit_for_layer(layer: str) -> str:
    if layer == "passthrough":
        return "passthrough"
    tool_id = LAYER_DEFAULT_TOOL.get(layer, layer)
    return credit_line(tool_id)


def candidates_for(category: str) -> list[str]:
    block = _profiles_data().get("candidates") or {}
    ordered = [str(item) for item in (block.get(category) or [])]
    if ordered:
        return ordered
    catalog_cat = CATALOG_CATEGORY.get(category, category)
    return [tool.id for tool in load_tools() if catalog_cat in tool.categories]


def tools_in_category(category: str) -> list[Tool]:
    ids = candidates_for(category)
    known = tools_by_id()
    extra = [
        tool
        for tool in load_tools()
        if CATALOG_CATEGORY.get(category, category) in tool.categories and tool.id not in ids
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
    if tool.status != "active":
        return "not wired in v1"
    if tool.extra:
        if core_only:
            return f"extra {tool.extra} skipped (--core-only)"
        if tool.extra not in extras:
            return f"extra {tool.extra} not installed"
    other = conflicts_with(tool.id, chosen)
    if other:
        return f"conflicts with {other}"
    return None

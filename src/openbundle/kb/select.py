"""Deterministic bundle picker. Walk candidates; skip incompatibles; never nag."""

from __future__ import annotations

from dataclasses import dataclass, field

from openbundle.init.scan import ScanResult, installed_extras
from openbundle.kb.catalog import (
    WRAP_CATEGORIES,
    Tool,
    candidates_for,
    get_tool,
    incompatibility,
    tools_in_category,
)


@dataclass
class CategoryChoice:
    category: str
    tool_id: str
    reasons: dict[str, str] = field(default_factory=dict)

    @property
    def skipped(self) -> bool:
        return self.tool_id in {"", "none"}


@dataclass
class Selection:
    cache: str
    memory: str
    compress: str
    profile: str
    extras: list[str]
    details: dict[str, CategoryChoice] = field(default_factory=dict)


def select(
    scan: ScanResult,
    extras: list[str] | None = None,
    *,
    approved_extras: bool | None = None,
    core_only: bool = False,
) -> Selection:
    # approved_extras kept for older callers: False behaves like core_only.
    if approved_extras is False:
        core_only = True
    found = extras if extras is not None else installed_extras()
    extra_set = set() if core_only else set(found)
    profile = "coding-agent" if scan.coding_agent else "api-app"
    chosen: list[str] = []
    details: dict[str, CategoryChoice] = {}
    picked = {"cache": "none", "memory": "none", "compress": "none"}
    for category in WRAP_CATEGORIES:
        choice = _pick_category(category, extra_set, chosen, core_only=core_only)
        details[category] = choice
        if not choice.skipped:
            picked[category] = choice.tool_id
            chosen.append(choice.tool_id)
    return Selection(
        cache=picked["cache"],
        memory=picked["memory"],
        compress=picked["compress"],
        profile=profile,
        extras=list(found),
        details=details,
    )


def _pick_category(
    category: str,
    extras: set[str],
    chosen: list[str],
    *,
    core_only: bool,
) -> CategoryChoice:
    reasons: dict[str, str] = {}
    winner = "none"
    for tool_id in candidates_for(category):
        tool = get_tool(tool_id)
        if tool is None:
            reasons[tool_id] = "not in catalog"
            continue
        why = incompatibility(tool, extras, chosen, core_only=core_only)
        if why:
            reasons[tool_id] = why
            continue
        if winner == "none":
            winner = tool.id
    for tool in tools_in_category(category):
        if tool.id not in reasons and tool.id != winner:
            why = incompatibility(tool, extras, chosen + ([winner] if winner != "none" else []), core_only=core_only)
            if why:
                reasons[tool.id] = why
    return CategoryChoice(category=category, tool_id=winner, reasons=reasons)


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
        rows.append((tool, incompatibility(tool, extra_set, taken, core_only=core_only)))
    return rows

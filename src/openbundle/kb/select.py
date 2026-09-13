"""Deterministic bundle picker. Wrap categories go live; batch stays advisory."""

from __future__ import annotations

from dataclasses import dataclass, field

from openbundle.init.scan import ScanResult, installed_extras
from openbundle.kb.catalog import (
    ADVISORY_CATEGORIES,
    ALL_PICK_CATEGORIES,
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
    live: bool = False
    reasons: dict[str, str] = field(default_factory=dict)

    @property
    def skipped(self) -> bool:
        return self.tool_id in {"", "none"}


@dataclass
class Selection:
    cache: str
    memory: str
    compress: str
    routing: str
    guardrails: str
    structured: str
    eval: str
    coalesce: str
    prompt_cache: str
    context: str
    batch: str
    profile: str
    extras: list[str]
    details: dict[str, CategoryChoice] = field(default_factory=dict)
    live: dict[str, bool] = field(default_factory=dict)


def select(
    scan: ScanResult,
    extras: list[str] | None = None,
    *,
    approved_extras: bool | None = None,
    core_only: bool = False,
    allow_lossy: bool = False,
) -> Selection:
    if approved_extras is False:
        core_only = True
    found = extras if extras is not None else installed_extras()
    extra_set = set() if core_only else set(found)
    profile = "coding-agent" if scan.coding_agent else "api-app"
    chosen: list[str] = []
    details: dict[str, CategoryChoice] = {}
    picked = {key: "none" for key in ALL_PICK_CATEGORIES}
    live: dict[str, bool] = {key: False for key in ALL_PICK_CATEGORIES}

    for category in WRAP_CATEGORIES:
        choice = _pick_category(category, extra_set, chosen, core_only=core_only)
        go_live = (not choice.skipped) and (category == "cache" or (allow_lossy and not core_only))
        if core_only and category != "cache":
            go_live = False
        choice.live = go_live
        details[category] = choice
        if not choice.skipped:
            picked[category] = choice.tool_id
            chosen.append(choice.tool_id)
            live[category] = go_live

    batch = _pick_category("batch", extra_set, chosen, core_only=True)
    batch.tool_id = picked.get("batch") or "provider_batch"
    batch.live = False
    batch.reasons.setdefault("provider_batch", "you add this yourself — not on the live path")
    details["batch"] = batch
    picked["batch"] = "none"
    live["batch"] = False

    return Selection(
        cache=picked["cache"],
        memory=picked["memory"],
        compress=picked["compress"],
        routing=picked["routing"],
        guardrails=picked["guardrails"],
        structured=picked["structured"],
        eval=picked["eval"],
        coalesce=picked["coalesce"],
        prompt_cache=picked["prompt_cache"],
        context=picked["context"],
        batch="none",
        profile=profile,
        extras=list(found),
        details=details,
        live=live,
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
            why = incompatibility(
                tool,
                extras,
                chosen + ([winner] if winner != "none" else []),
                core_only=core_only,
            )
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
        if category in ADVISORY_CATEGORIES:
            rows.append((tool, "you add this yourself — not on the live path"))
            continue
        rows.append((tool, incompatibility(tool, extra_set, taken, core_only=core_only)))
    return rows

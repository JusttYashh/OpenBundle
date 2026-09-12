"""Named, credited CLI text. Init stays short; config has specific skip reasons."""

from __future__ import annotations

from openbundle.kb.catalog import INIT_SKIP_GENERIC, WRAP_CATEGORIES, credit_line, get_tool
from openbundle.kb.select import Selection, explain_category

CATEGORY_LABEL = {
    "cache": "cache",
    "memory": "memory",
    "compress": "compression",
}


def format_init_summary(choice: Selection) -> str:
    lines = ["OpenBundle initialized. Active tools:"]
    for category in WRAP_CATEGORIES:
        label = f"{CATEGORY_LABEL[category]:<12}"
        tool_id = getattr(choice, category)
        if tool_id and tool_id != "none":
            lines.append(f"  ✓ {label} → {credit_line(tool_id)}")
        else:
            lines.append(f"  ✗ {label} → skipped ({INIT_SKIP_GENERIC})")
    lines.extend(
        [
            "",
            "OpenBundle does not replace these tools — it selects, configures, and",
            "runs them together for you. Full credits: CREDITS.md",
        ]
    )
    return "\n".join(lines)


def format_config_view(
    extras: list[str],
    *,
    active: dict[str, str],
    core_only: bool = False,
) -> str:
    chosen = [active[c] for c in WRAP_CATEGORIES if active.get(c) not in (None, "", "none")]
    blocks: list[str] = []
    for category in WRAP_CATEGORIES:
        current = active.get(category) or "none"
        title = CATEGORY_LABEL[category]
        if current != "none":
            head = f"{title}: {credit_line(current)}"
        else:
            head = f"{title}: off"
        lines = [head]
        others = chosen if current == "none" else [c for c in chosen if c != current]
        for tool, why in explain_category(category, extras, chosen=others, core_only=core_only):
            if why:
                lines.append(f"  - {tool.id:<18} {why}")
            elif tool.id == current:
                lines.append(f"  - {tool.id:<18} active  {tool.credited()}")
            else:
                lines.append(f"  - {tool.id:<18} available  {tool.credited()}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def apply_bundle_to_doc(doc: dict, category: str, tool_id: str) -> None:
    bundle = doc.setdefault("bundle", {})
    layers = doc.setdefault("layers", {})
    if category == "cache":
        bundle["cache"] = tool_id
        layers.setdefault("cache", {})["enabled"] = tool_id != "none"
    elif category == "memory":
        bundle["memory"] = tool_id
        memory = layers.setdefault("memory", {})
        memory["enabled"] = tool_id != "none"
        memory["adapter"] = "mem0" if tool_id == "mem0" else "summary"
    elif category == "compress":
        bundle["compress"] = tool_id
        compress = layers.setdefault("compress", {})
        compress["enabled"] = tool_id != "none"
        compress["adapter"] = "llmlingua2" if tool_id == "llmlingua2" else tool_id


def active_from_doc(doc: dict) -> dict[str, str]:
    bundle = doc.get("bundle") or {}
    return {
        "cache": str(bundle.get("cache") or "none"),
        "memory": str(bundle.get("memory") or "none"),
        "compress": str(bundle.get("compress") or "none"),
    }


def get_tool_or_none(tool_id: str):
    return get_tool(tool_id)

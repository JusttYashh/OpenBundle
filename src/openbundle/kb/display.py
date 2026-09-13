"""Named, credited CLI text. Init stays short; config has specific skip reasons."""

from __future__ import annotations

from openbundle.kb.catalog import (
    ADVISORY_CATEGORIES,
    ALL_PICK_CATEGORIES,
    INIT_SKIP_GENERIC,
    WRAP_CATEGORIES,
    credit_line,
    get_tool,
)
from openbundle.kb.select import Selection, explain_category

CATEGORY_LABEL = {
    "cache": "cache",
    "coalesce": "coalesce",
    "compress": "compression",
    "prompt_cache": "prompt-cache",
    "routing": "routing",
    "guardrails": "guardrails",
    "structured": "structured",
    "eval": "eval",
    "memory": "memory",
    "context": "context",
    "batch": "batch",
}


def format_init_summary(choice: Selection) -> str:
    lines = ["OpenBundle initialized. Active tools:"]
    for category in WRAP_CATEGORIES:
        label = f"{CATEGORY_LABEL[category]:<12}"
        tool_id = getattr(choice, category)
        live = choice.live.get(category, False)
        if tool_id and tool_id != "none" and live:
            lines.append(f"  ✓ {label} → {credit_line(tool_id)}")
        elif tool_id and tool_id != "none":
            lines.append(f"  ○ {label} → {credit_line(tool_id)} (waiting for traffic sample)")
        else:
            lines.append(f"  ✗ {label} → skipped ({INIT_SKIP_GENERIC})")
    lines.extend(
        [
            "",
            "You add this yourself:",
            "  batch        → Anthropic / OpenAI Batch API (~50% off, no streaming)",
            "                 Use for nightly evals and bulk jobs — never on live chat.",
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
    wrap_ids = [active[c] for c in WRAP_CATEGORIES if active.get(c) not in (None, "", "none")]
    blocks: list[str] = ["On the live path:"]
    for category in WRAP_CATEGORIES:
        current = active.get(category) or "none"
        title = CATEGORY_LABEL[category]
        if current != "none":
            head = f"{title}: {credit_line(current)}"
        else:
            head = f"{title}: off"
        lines = [head]
        others = wrap_ids if current == "none" else [c for c in wrap_ids if c != current]
        for tool, why in explain_category(category, extras, chosen=others, core_only=core_only):
            if why:
                lines.append(f"  - {tool.id:<22} {why}")
            elif tool.id == current:
                lines.append(f"  - {tool.id:<22} active  {tool.credited()}")
            else:
                lines.append(f"  - {tool.id:<22} available  {tool.credited()}")
        blocks.append("\n".join(lines))
    blocks.append("You add this yourself:")
    for category in ADVISORY_CATEGORIES:
        lines = [f"{CATEGORY_LABEL[category]}: off (not on the live path)"]
        for tool, why in explain_category(category, extras, core_only=core_only):
            lines.append(f"  - {tool.id:<22} {why or 'you add this yourself — not on the live path'}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def apply_bundle_to_doc(doc: dict, category: str, tool_id: str) -> None:
    bundle = doc.setdefault("bundle", {})
    layers = doc.setdefault("layers", {})
    if category == "batch":
        bundle["batch"] = "none"
        layers.setdefault("batch", {})["enabled"] = False
        return
    bundle[category] = tool_id
    layer = layers.setdefault(category, {})
    layer["enabled"] = tool_id != "none"
    if category == "compress":
        layer["adapter"] = "llmlingua2" if tool_id == "llmlingua2" else tool_id
    elif category == "memory":
        layer["adapter"] = "mem0" if tool_id == "mem0" else "summary"
    elif tool_id != "none":
        layer["adapter"] = tool_id


def active_from_doc(doc: dict) -> dict[str, str]:
    bundle = doc.get("bundle") or {}
    out = {}
    for key in ALL_PICK_CATEGORIES:
        out[key] = str(bundle.get(key) or "none")
    return out


def get_tool_or_none(tool_id: str):
    return get_tool(tool_id)

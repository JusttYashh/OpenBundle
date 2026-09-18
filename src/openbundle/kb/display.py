"""Named, credited CLI text. Init stays short; status is the live number."""

from __future__ import annotations

from openbundle.kb.catalog import (
    ADVISORY_CATEGORIES,
    INIT_SKIP_GENERIC,
    credit_line,
    get_tool,
)
from openbundle.pipeline.jobs import HOSTED_JOB_IDS, JOB_BY_ID, SELF_HOSTED_JOB_IDS
from openbundle.kb.select import Selection, explain_category


def format_init_summary(choice: Selection) -> str:
    lines = ["OpenBundle initialized. Jobs:"]
    for job_id in HOSTED_JOB_IDS:
        spec = JOB_BY_ID[job_id]
        label = f"{spec.label:<22}"
        tool_id = choice.jobs.get(job_id) or "none"
        live = choice.live.get(job_id, False)
        if tool_id and tool_id != "none" and live:
            lines.append(f"  ✓ {label} → {credit_line(tool_id)}")
        elif tool_id and tool_id != "none" and spec.tier == "B":
            lines.append(f"  … {label} → {credit_line(tool_id)} (warming or extra not installed)")
        elif tool_id and tool_id != "none":
            lines.append(f"  ○ {label} → {credit_line(tool_id)}")
        else:
            lines.append(f"  ✗ {label} → skipped ({INIT_SKIP_GENERIC})")
    if choice.local_inference:
        lines.append("")
        lines.append("Self-hosted inference detected — not live in this sidecar until constructed:")
        for job_id in SELF_HOSTED_JOB_IDS:
            tool_id = choice.jobs.get(job_id) or "none"
            if tool_id != "none":
                lines.append(
                    f"  ○ {JOB_BY_ID[job_id].label:<22} → {credit_line(tool_id)} "
                    "(engine-side, not verified together)"
                )
    lines.extend(
        [
            "",
            "Advisory (never on the live path):",
            "  memory       → Mem0, Zep, Letta, Cognee, Supermemory, LangMem, MemPalace",
            "  batch        → Anthropic / OpenAI Batch API (~50% off, no streaming)",
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
    wrap_ids = [active[c] for c in HOSTED_JOB_IDS if active.get(c) not in (None, "", "none")]
    blocks: list[str] = ["On the live path:"]
    for job_id in HOSTED_JOB_IDS:
        current = active.get(job_id) or "none"
        title = JOB_BY_ID[job_id].label
        if current != "none":
            head = f"{title}: {credit_line(current)}"
        else:
            head = f"{title}: off"
        lines = [head]
        others = wrap_ids if current == "none" else [c for c in wrap_ids if c != current]
        for tool, why in explain_category(job_id, extras, chosen=others, core_only=core_only):
            if why:
                lines.append(f"  - {tool.id:<22} {why}")
            elif tool.id == current:
                lines.append(f"  - {tool.id:<22} active  {tool.credited()}")
            else:
                lines.append(f"  - {tool.id:<22} available  {tool.credited()}")
        blocks.append("\n".join(lines))
    blocks.append("You add this yourself:")
    for category in ADVISORY_CATEGORIES:
        lines = [f"{category}: off (not on the live path)"]
        for tool, why in explain_category(category, extras, core_only=core_only):
            lines.append(f"  - {tool.id:<22} {why or 'you add this yourself — not on the live path'}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def apply_bundle_to_doc(doc: dict, category: str, tool_id: str) -> None:
    bundle = doc.setdefault("bundle", {})
    jobs = doc.setdefault("jobs", {})
    layers = doc.setdefault("layers", {})
    if category in ADVISORY_CATEGORIES:
        bundle[category] = "none"
        jobs[category] = False
        return
    bundle[category] = tool_id
    jobs[category] = tool_id != "none"
    if category == "compress":
        layer = layers.setdefault("compress", {})
        layer["enabled"] = tool_id != "none"
        layer["adapter"] = "llmlingua2" if tool_id == "llmlingua2" else tool_id
    if category == "exact_hash":
        layers.setdefault("cache", {})["enabled"] = tool_id != "none"


def active_from_doc(doc: dict) -> dict[str, str]:
    bundle = doc.get("bundle") or {}
    out = {}
    for key in list(HOSTED_JOB_IDS) + list(ADVISORY_CATEGORIES) + list(SELF_HOSTED_JOB_IDS):
        out[key] = str(bundle.get(key) or "none")
    return out


def get_tool_or_none(tool_id: str):
    return get_tool(tool_id)

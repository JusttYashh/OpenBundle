"""Named, credited CLI text. Init stays short; status is the live number."""

from __future__ import annotations

import os

from openbundle.config import DEFAULT_HOST, DEFAULT_PORT
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
    if choice.with_lynx:
        lines.append("")
        lines.append(
            "  ○ RAG faithfulness      → Patronus Lynx-8B "
            "(conditional; live only if local weights construct)"
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
    if choice.openrouter:
        lines.extend(
            [
                "",
                "Upstream: OpenRouter (OPENROUTER_API_KEY). Both Anthropic and OpenAI",
                "paths on the sidecar forward there. Agents still attach to 127.0.0.1.",
            ]
        )
    return "\n".join(lines)


def format_attach_instructions(*, listen: str | None = None, shell: str | None = None) -> str:
    """How coding agents talk to this sidecar — not to OpenRouter directly."""
    listen = listen or f"{DEFAULT_HOST}:{DEFAULT_PORT}"
    host = f"http://{listen}"
    openai_base = f"{host}/v1"
    powershell = (shell or ("powershell" if os.name == "nt" else "bash")) == "powershell"
    lines = [
        "Attach a coding agent to this sidecar (not to OpenRouter/Anthropic directly).",
        "The sidecar reads OPENROUTER_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY from its own environment.",
        "",
    ]
    if powershell:
        lines.extend(
            [
                "Claude Code (this PowerShell session, then `claude`):",
                f'  $env:ANTHROPIC_BASE_URL = "{host}"',
                '  $env:ANTHROPIC_AUTH_TOKEN = "openbundle"',
                '  $env:ANTHROPIC_API_KEY = ""',
                "",
                "Codex / OpenAI-compatible CLIs:",
                f'  $env:OPENAI_BASE_URL = "{openai_base}"',
                '  $env:OPENAI_API_KEY = "openbundle"',
            ]
        )
    else:
        lines.extend(
            [
                "Claude Code (this shell, then `claude`):",
                f"  export ANTHROPIC_BASE_URL={host}",
                "  export ANTHROPIC_AUTH_TOKEN=openbundle",
                '  export ANTHROPIC_API_KEY=""',
                "",
                "Codex / OpenAI-compatible CLIs:",
                f"  export OPENAI_BASE_URL={openai_base}",
                "  export OPENAI_API_KEY=openbundle",
            ]
        )
    lines.extend(
        [
            "",
            "Cursor: Settings → Models → OpenAI-compatible (or override OpenAI base URL)",
            f"  Base URL: {openai_base}",
            "  API key:  openbundle",
            "",
            "Aider:",
            f"  aider --openai-api-base {openai_base} --openai-api-key openbundle",
            "",
            "If Claude Code was logged into Anthropic before, run `/logout` once, restart, then `/status`.",
            "The base URL must be the sidecar — no trailing /v1 on ANTHROPIC_BASE_URL.",
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

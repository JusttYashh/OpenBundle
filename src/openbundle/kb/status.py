"""openbundle status — live number, with a loud DEGRADED banner."""

from __future__ import annotations

from openbundle.kb.catalog import credit_line
from openbundle.pipeline.jobs import JOB_BY_ID, STATUS_JOB_IDS
from openbundle.pipeline.registry import StageRegistry


def format_status(registry: StageRegistry, *, overlay_on: bool = True) -> str:
    lines: list[str] = []
    degraded = registry.degraded_jobs()
    if overlay_on and degraded:
        for job_id, err in degraded:
            spec = JOB_BY_ID.get(job_id)
            label = spec.label if spec else job_id
            lines.append(f"DEGRADED: {label} — {err}")
        lines.append("")

    lines.append("OpenBundle status")
    if not overlay_on:
        lines.append("overlay: off (passthrough)")
        return "\n".join(lines)

    infos = registry.info_snapshot()
    constructed = set(registry.snapshot())
    lines.append(f"{'job':<22} {'state':<10} tool")
    for job_id in STATUS_JOB_IDS:
        info = infos.get(job_id)
        if info is None:
            continue
        spec = JOB_BY_ID[job_id]
        state = info.state
        if state == "live" and job_id not in constructed:
            state = "off"
        tool = credit_line(info.tool_id)
        extra = ""
        if state == "off" and info.reason:
            extra = f"  ({info.reason})"
        if state == "warming":
            extra = "  (quiet)"
        lines.append(f"{spec.label:<22} {state:<10} {tool}{extra}")

    lines.append("")
    lines.append(f"fail_open_count: {registry.fail_open_count}")
    lines.append(f"nemo_rail_tokens: {registry.nemo_rail_tokens}")
    if registry.nemo_rail_ms:
        lines.append(f"nemo_rail_ms: {registry.nemo_rail_ms:.0f}")
    if registry.lynx_constructed():
        lines.append("rag_faithfulness: Lynx-8B")
    else:
        lines.append("rag_faithfulness: heuristic (not Lynx)")
    lines.append(f"obs: {'self-host' if registry.local_obs else 'vendor hosted free tier'}")
    return "\n".join(lines)

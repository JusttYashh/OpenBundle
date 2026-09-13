"""CREDITS.md is regenerated on every init from the full catalog."""

from __future__ import annotations

from pathlib import Path

from openbundle.kb.catalog import load_tools


def render_credits() -> str:
    lines = [
        "# Credits",
        "",
        "OpenBundle does not replace these tools — it selects, configures, and runs",
        "compatible ones together. Every tool in the catalog is listed here, whether",
        "or not it is active on this machine.",
        "",
        "Also at: https://openbundle.dev/credits",
        "",
    ]
    for tool in load_tools():
        license_s = tool.license or "see project"
        lane = tool.lane or "catalog_only"
        if tool.url:
            lines.append(f"- [{tool.name}]({tool.url}) — {license_s} — {lane}")
        else:
            lines.append(f"- {tool.name} — {license_s} — {lane}")
        if tool.credit_line:
            lines.append(f"  {tool.credit_line}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_credits(path: Path | None = None) -> Path:
    dest = path or (Path.cwd() / "CREDITS.md")
    dest.write_text(render_credits(), encoding="utf-8")
    return dest

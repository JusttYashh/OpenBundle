"""README / CATALOG.md — generated from catalog.yaml. User docs hide research-only rows."""

from __future__ import annotations

from openbundle.kb.catalog import job_headline_counts, load_tools
from openbundle.pipeline.jobs import CONDITIONAL_JOBS, HOSTED_JOBS

START = "<!-- CATALOG:START -->"
END = "<!-- CATALOG:END -->"
HERO_START = "<!-- HERO:START -->"
HERO_END = "<!-- HERO:END -->"

def lane_titles() -> dict[str, str]:
    hosted, extra, _advisory = job_headline_counts()
    return {
        "hosted": f"{hosted} jobs for hosted APIs",
        "self_hosted": f"{extra} more if local inference / --with-lynx",
        "advisory": "Advisory — not on the live path",
    }


def shipping_tools():
    return [
        tool
        for tool in load_tools()
        if tool.role == "primary" or tool.lane == "advisory"
    ]


def catalog_counts() -> tuple[int, int, int]:
    hosted, self_hosted, advisory = job_headline_counts()
    return hosted, self_hosted, advisory


def render_hero_line() -> str:
    hosted, extra, _advisory = job_headline_counts()
    total = hosted + extra
    return (
        f"**{hosted} hosted-API jobs + {extra} conditional = {total} named tools.** "
        "`openbundle status` is the live number on this traffic — not a multiplied ceiling.\n"
    )


def render_readme_summary() -> str:
    hosted, extra, advisory = job_headline_counts()
    return (
        f"**{hosted} live jobs** for hosted-API users, **{extra}** more if self-hosted "
        f"inference or `--with-lynx` is detected, plus **{advisory}** advisory tools (memory + batch). "
        f"`openbundle status` is the live number. Full table: [CATALOG.md](CATALOG.md) · "
        "credits: [CREDITS.md](CREDITS.md).\n"
    )


def render_catalog_block() -> str:
    hosted, extra, advisory = job_headline_counts()
    lines = [
        (
            f"OpenBundle runs **{hosted}** distinct jobs for hosted APIs, plus **{extra}** "
            f"if local inference / `--with-lynx` is detected. **{advisory}** tools are advisory (never in the live path)."
        ),
        "",
    ]
    lines.extend(_job_tables("###"))
    return "\n".join(lines).rstrip() + "\n"


def render_catalog_page() -> str:
    hosted, extra, advisory = job_headline_counts()
    lines = [
        "# Catalog",
        "",
        (
            f"OpenBundle runs **{hosted}** distinct jobs for hosted APIs, plus **{extra}** "
            f"if local inference / `--with-lynx` is detected. **{advisory}** tools are advisory (never in the live path)."
        ),
        "",
    ]
    lines.extend(_job_tables("##"))
    return "\n".join(lines).rstrip() + "\n"


def _job_tables(heading: str) -> list[str]:
    by_id = {tool.id: tool for tool in load_tools()}
    titles = lane_titles()
    lines: list[str] = []

    lines.append(f"{heading} {titles['hosted']}")
    lines.append("")
    lines.append("| Job | Tool | License | Tier |")
    lines.append("|---|---|---|---|")
    for job in HOSTED_JOBS:
        tool = by_id.get(job.tool_id)
        if tool is None:
            continue
        name = f"[{tool.name}]({tool.url})" if tool.url else tool.name
        lines.append(f"| {job.label} | {name} | {tool.license or 'see project'} | {job.tier} |")
    lines.append("")

    lines.append(f"{heading} {titles['self_hosted']}")
    lines.append("")
    lines.append("LMCache, kvcached, and KVzip are not verified to work together.")
    lines.append("RAG faithfulness (Lynx) is conditional — not one of the 22 hosted jobs.")
    lines.append("")
    lines.append("| Job | Tool | License |")
    lines.append("|---|---|---|")
    for job in CONDITIONAL_JOBS:
        tool = by_id.get(job.tool_id)
        if tool is None:
            continue
        name = f"[{tool.name}]({tool.url})" if tool.url else tool.name
        lines.append(f"| {job.label} | {name} | {tool.license or 'see project'} |")
    lines.append("")

    lines.append(f"{heading} {titles['advisory']}")
    lines.append("")
    lines.append("| Tool | License |")
    lines.append("|---|---|")
    for tool in load_tools():
        if tool.lane != "advisory":
            continue
        name = f"[{tool.name}]({tool.url})" if tool.url else tool.name
        lines.append(f"| {name} | {tool.license or 'see project'} |")
    lines.append("")
    return lines


def _replace_section(readme: str, start: str, end: str, body: str) -> str:
    if start not in readme or end not in readme:
        raise ValueError(f"README.md must contain {start} and {end} markers")
    before, rest = readme.split(start, 1)
    _old, after = rest.split(end, 1)
    return f"{before}{start}\n{body}{end}{after}"


def replace_catalog_section(readme: str, block: str | None = None) -> str:
    body = block if block is not None else render_readme_summary()
    return _replace_section(readme, START, END, body)


def replace_hero_section(readme: str, block: str | None = None) -> str:
    body = block if block is not None else render_hero_line()
    return _replace_section(readme, HERO_START, HERO_END, body)


def replace_generated_sections(readme: str) -> str:
    return replace_catalog_section(replace_hero_section(readme))

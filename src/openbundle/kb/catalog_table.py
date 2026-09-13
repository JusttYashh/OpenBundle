"""README / CATALOG.md — generated from catalog.yaml. User docs hide research-only rows."""

from __future__ import annotations

from collections import defaultdict

from openbundle.kb.catalog import lane_counts, load_tools

START = "<!-- CATALOG:START -->"
END = "<!-- CATALOG:END -->"

LEAD_CATEGORIES = (
    "caching",
    "coalesce",
    "prompt_caching",
    "prompt_compression",
    "agent_memory",
    "context_management",
    "routing",
    "guardrails",
    "evaluation",
    "structured_output",
    "batch",
)
CATEGORY_TITLES = {
    "caching": "Cache",
    "coalesce": "Coalesce",
    "prompt_caching": "Prompt cache",
    "agent_memory": "Memory",
    "prompt_compression": "Compression",
    "context_management": "Context",
    "routing": "Routing",
    "guardrails": "Guardrails",
    "evaluation": "Evaluation",
    "structured_output": "Structured output",
    "batch": "Batch",
    "observability": "Reporting",
}
LANE_TITLES = {
    "wrap": "Wired and coming next",
    "advisory": "You add this yourself",
}


def _title(category: str) -> str:
    return CATEGORY_TITLES.get(category, category.replace("_", " ").title())


def _status_cell(status: str) -> str:
    if status == "active":
        return "on today"
    return "coming next"


def _name_cell(name: str, url: str) -> str:
    if url:
        return f"[{name}]({url})"
    return name


def shipping_tools():
    return [tool for tool in load_tools() if tool.lane in {"wrap", "advisory"}]


def catalog_counts() -> tuple[int, int, int]:
    tools = shipping_tools()
    categories: set[str] = set()
    active = 0
    for tool in tools:
        categories.update(tool.categories)
        if tool.status == "active":
            active += 1
    return len(tools), len(categories), active


def render_readme_summary() -> str:
    n_tools, n_cats, n_active = catalog_counts()
    lanes = lane_counts()
    return (
        f"**{n_tools} tools we ship or recommend** across **{n_cats}** categories — "
        f"**{n_active}** on today, {lanes['advisory']} you add yourself (Batch API). "
        "Full table: [CATALOG.md](CATALOG.md) · credits: [CREDITS.md](CREDITS.md).\n"
    )


def render_catalog_block() -> str:
    n_tools, n_cats, n_active = catalog_counts()
    lines = [
        (
            f"OpenBundle ships or recommends **{n_tools}** tools across **{n_cats}** categories. "
            f"**{n_active}** are wired today."
        ),
        "",
    ]
    lines.extend(_lane_tables("###"))
    return "\n".join(lines).rstrip() + "\n"


def render_catalog_page() -> str:
    n_tools, n_cats, n_active = catalog_counts()
    lines = [
        "# Catalog",
        "",
        (
            f"OpenBundle ships or recommends **{n_tools}** tools across **{n_cats}** categories. "
            f"**{n_active}** are wired today."
        ),
        "",
    ]
    lines.extend(_lane_tables("##"))
    return "\n".join(lines).rstrip() + "\n"


def _lane_tables(heading: str) -> list[str]:
    by_lane: dict[str, list] = defaultdict(list)
    for tool in shipping_tools():
        by_lane[tool.lane].append(tool)
    lines: list[str] = []
    for lane in ("wrap", "advisory"):
        rows = by_lane.get(lane) or []
        if not rows:
            continue
        lines.append(f"{heading} {LANE_TITLES[lane]}")
        lines.append("")
        grouped: dict[str, list] = defaultdict(list)
        for tool in rows:
            for category in tool.categories:
                grouped[category].append(tool)
        ordered = [c for c in LEAD_CATEGORIES if c in grouped]
        ordered.extend(sorted(c for c in grouped if c not in LEAD_CATEGORIES))
        for category in ordered:
            cat_rows = grouped[category]
            cat_rows.sort(key=lambda t: (0 if t.status == "active" else 1, t.name.lower()))
            sub = "####" if heading == "###" else "###"
            lines.append(f"{sub} {_title(category)}")
            lines.append("")
            lines.append("| Tool | License | Status |")
            lines.append("|---|---|---|")
            for tool in cat_rows:
                license_s = tool.license or "see project"
                lines.append(
                    f"| {_name_cell(tool.name, tool.url)} | {license_s} | {_status_cell(tool.status)} |"
                )
            lines.append("")
    return lines


def replace_catalog_section(readme: str, block: str | None = None) -> str:
    body = block if block is not None else render_readme_summary()
    if START not in readme or END not in readme:
        raise ValueError(f"README.md must contain {START} and {END} markers")
    before, rest = readme.split(START, 1)
    _old, after = rest.split(END, 1)
    return f"{before}{START}\n{body}{END}{after}"

"""README catalog table — generated from catalog.yaml, never hand-maintained."""

from __future__ import annotations

from collections import defaultdict

from openbundle.kb.catalog import lane_counts, load_tools

START = "<!-- CATALOG:START -->"
END = "<!-- CATALOG:END -->"

LEAD_CATEGORIES = (
    "caching",
    "prompt_compression",
    "routing",
    "guardrails",
    "evaluation",
    "structured_output",
    "agent_memory",
)
CATEGORY_TITLES = {
    "caching": "Cache",
    "agent_memory": "Memory (advisory)",
    "prompt_compression": "Compression",
    "quantization": "Quantization",
    "serving": "Serving",
    "routing": "Routing",
    "speculative_decoding": "Speculative decoding",
    "attention": "Attention",
    "fine_tuning": "Fine-tuning",
    "orchestration": "Orchestration",
    "rag": "RAG",
    "guardrails": "Guardrails",
    "observability": "Observability",
    "prompt_optimization": "Prompt optimization",
    "coding_agent": "Coding-agent tools",
    "evaluation": "Evaluation",
    "structured_output": "Structured output",
}
LANE_TITLES = {
    "wrap": "Wrap-eligible (proxy can run these)",
    "advisory": "Advisory only (never auto-enabled)",
    "catalog_only": "Structurally out of scope (not wireable into a proxy)",
}


def _title(category: str) -> str:
    return CATEGORY_TITLES.get(category, category.replace("_", " ").title())


def _status_cell(status: str) -> str:
    if status == "active":
        return "active in v2 (wired)"
    return "mapped — not wired yet"


def _name_cell(name: str, url: str) -> str:
    if url:
        return f"[{name}]({url})"
    return name


def catalog_counts() -> tuple[int, int, int]:
    tools = load_tools()
    categories: set[str] = set()
    active = 0
    for tool in tools:
        categories.update(tool.categories)
        if tool.status == "active":
            active += 1
    return len(tools), len(categories), active


def render_catalog_block() -> str:
    tools = load_tools()
    n_tools, n_cats, n_active = catalog_counts()
    lanes = lane_counts()
    lines = [
        (
            f"OpenBundle tracks **{n_tools}** open-source tools across **{n_cats}** categories "
            f"({lanes['wrap']} wrap-eligible, {lanes['advisory']} advisory, "
            f"{lanes['catalog_only']} catalog-only). "
            f"**{n_active}** have a wired adapter today; the rest are catalogued, "
            "licensed, and ready to be adapted next — see [CREDITS.md](CREDITS.md) and open an "
            "issue/PR to help wire one in."
        ),
        "",
    ]
    by_lane: dict[str, list] = defaultdict(list)
    seen: set[str] = set()
    for tool in tools:
        by_lane[tool.lane].append(tool)
    for lane in ("wrap", "advisory", "catalog_only"):
        rows = by_lane.get(lane) or []
        if not rows:
            continue
        lines.append(f"### {LANE_TITLES[lane]}")
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
            lines.append(f"#### {_title(category)}")
            lines.append("")
            lines.append("| Tool | License | Status |")
            lines.append("|---|---|---|")
            for tool in cat_rows:
                license_s = tool.license or "see project"
                lines.append(
                    f"| {_name_cell(tool.name, tool.url)} | {license_s} | {_status_cell(tool.status)} |"
                )
                seen.add(tool.id)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def replace_catalog_section(readme: str, block: str | None = None) -> str:
    body = block if block is not None else render_catalog_block()
    if START not in readme or END not in readme:
        raise ValueError(f"README.md must contain {START} and {END} markers")
    before, rest = readme.split(START, 1)
    _old, after = rest.split(END, 1)
    return f"{before}{START}\n{body}{END}{after}"

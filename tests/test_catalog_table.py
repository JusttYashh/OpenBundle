from pathlib import Path

from openbundle.kb.catalog import load_tools
from openbundle.kb.catalog_table import (
    END,
    START,
    catalog_counts,
    render_catalog_block,
    replace_catalog_section,
)


def test_catalog_block_lists_all_tools_and_statuses():
    tools = load_tools()
    n_tools, n_cats, n_active = catalog_counts()
    block = render_catalog_block()
    assert str(n_tools) in block
    assert str(n_cats) in block
    assert str(n_active) in block
    assert "active in v2 (wired)" in block
    assert "mapped — not wired yet" in block
    assert "Wrap-eligible" in block
    assert "Advisory only" in block
    assert "GPTCache" in block
    assert "vLLM" in block
    assert "OpenBundle exact-hash cache" in block
    for tool in tools:
        assert tool.name in block
        if tool.url:
            assert tool.url in block


def test_replace_catalog_section_roundtrip():
    stub = f"before\n{START}\nold\n{END}\nafter\n"
    updated = replace_catalog_section(stub, "NEW\n")
    assert "old" not in updated
    assert f"{START}\nNEW\n{END}" in updated


def test_readme_has_markers():
    text = Path("README.md").read_text(encoding="utf-8")
    assert START in text
    assert END in text

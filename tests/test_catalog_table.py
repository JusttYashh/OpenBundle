from pathlib import Path

from openbundle.kb.catalog_table import (
    END,
    START,
    catalog_counts,
    render_catalog_block,
    render_readme_summary,
    replace_catalog_section,
    shipping_tools,
)


def test_catalog_block_lists_shipping_tools():
    tools = shipping_tools()
    n_tools, n_cats, n_active = catalog_counts()
    block = render_catalog_block()
    assert str(n_tools) in block
    assert str(n_cats) in block
    assert str(n_active) in block
    assert "on today" in block
    assert "coming next" in block
    assert "Wired and coming next" in block
    assert "You add this yourself" in block
    assert "out of scope" not in block.lower()
    assert "catalog-only" not in block.lower()
    assert "GPTCache" in block
    assert "OpenBundle exact-hash cache" in block
    assert "vLLM" not in block
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
    assert render_readme_summary().strip() in text
    assert "out of scope" not in text.lower()
    assert Path("CATALOG.md").is_file()

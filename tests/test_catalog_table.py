from pathlib import Path

from openbundle.kb.catalog import job_headline_counts
from openbundle.kb.catalog_table import (
    END,
    HERO_END,
    HERO_START,
    START,
    lane_titles,
    render_catalog_block,
    render_hero_line,
    render_readme_summary,
    replace_catalog_section,
    replace_hero_section,
    shipping_tools,
)
from openbundle.pipeline.jobs import HOSTED_JOB_COUNT, SELF_HOSTED_JOB_COUNT


def test_catalog_block_lists_shipping_tools():
    hosted, self_hosted, advisory = job_headline_counts()
    block = render_catalog_block()
    assert str(hosted) in block
    assert str(self_hosted) in block
    assert hosted == HOSTED_JOB_COUNT
    assert self_hosted == SELF_HOSTED_JOB_COUNT
    assert lane_titles()["hosted"] in block
    assert "not verified to work together" in block
    assert "GPTCache" in block
    assert "OpenBundle exact-hash cache" in block
    assert "vLLM" not in block
    for tool in shipping_tools():
        assert tool.name in block
        if tool.url:
            assert tool.url in block


def test_replace_catalog_section_roundtrip():
    stub = f"before\n{START}\nold\n{END}\nafter\n"
    updated = replace_catalog_section(stub, "NEW\n")
    assert "old" not in updated
    assert f"{START}\nNEW\n{END}" in updated


def test_replace_hero_section_roundtrip():
    stub = f"before\n{HERO_START}\nold\n{HERO_END}\nafter\n"
    updated = replace_hero_section(stub, "NEW\n")
    assert "old" not in updated
    assert f"{HERO_START}\nNEW\n{HERO_END}" in updated


def test_readme_has_markers():
    text = Path("README.md").read_text(encoding="utf-8")
    assert START in text
    assert END in text
    assert HERO_START in text
    assert HERO_END in text
    assert render_readme_summary().strip() in text
    assert render_hero_line().strip() in text
    assert Path("CATALOG.md").is_file()


def test_readme_hero_is_generated_not_hand_typed():
    hosted, self_hosted, _advisory = job_headline_counts()
    total = hosted + self_hosted
    text = Path("README.md").read_text(encoding="utf-8")
    hero = text.split(HERO_START, 1)[1].split(HERO_END, 1)[0]
    catalog = text.split(START, 1)[1].split(END, 1)[0]
    assert render_hero_line().strip() == hero.strip()
    assert str(hosted) in hero
    assert str(self_hosted) in hero
    assert str(total) in hero
    remainder = text.replace(hero, "").replace(catalog, "")
    # 127.0.0.1 contains the substring "27"; ignore IPs.
    import re

    cleaned = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "", remainder)
    assert str(total) not in cleaned


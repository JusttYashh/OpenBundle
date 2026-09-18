#!/usr/bin/env python3
"""Regenerate README catalog table and CREDITS.md from catalog.yaml.

Init also rewrites CREDITS.md. This script is the CI/release sync so README
cannot drift from the same catalog.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from openbundle.kb.catalog_table import (  # noqa: E402
    render_catalog_page,
    replace_generated_sections,
)
from openbundle.kb.credits import render_credits  # noqa: E402


def sync(*, check: bool = False) -> int:
    readme_path = ROOT / "README.md"
    catalog_path = ROOT / "CATALOG.md"
    credits_path = ROOT / "CREDITS.md"
    new_readme = replace_generated_sections(readme_path.read_text(encoding="utf-8"))
    new_catalog = render_catalog_page()
    new_credits = render_credits()
    old_readme = readme_path.read_text(encoding="utf-8")
    old_catalog = catalog_path.read_text(encoding="utf-8") if catalog_path.is_file() else ""
    old_credits = credits_path.read_text(encoding="utf-8") if credits_path.is_file() else ""
    if check:
        dirty = []
        if new_readme != old_readme:
            dirty.append("README.md")
        if new_catalog != old_catalog:
            dirty.append("CATALOG.md")
        if new_credits != old_credits:
            dirty.append("CREDITS.md")
        if dirty:
            print("Catalog docs are stale. Run: python scripts/gen_readme_catalog.py", file=sys.stderr)
            print("Out of date: " + ", ".join(dirty), file=sys.stderr)
            return 1
        print("Catalog docs are in sync.")
        return 0
    readme_path.write_text(new_readme, encoding="utf-8")
    catalog_path.write_text(new_catalog, encoding="utf-8")
    credits_path.write_text(new_credits, encoding="utf-8")
    print(
        f"Updated {readme_path.relative_to(ROOT)}, "
        f"{catalog_path.relative_to(ROOT)}, and {credits_path.relative_to(ROOT)}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if README.md or CREDITS.md would change.",
    )
    return sync(check=parser.parse_args().check)


if __name__ == "__main__":
    raise SystemExit(main())

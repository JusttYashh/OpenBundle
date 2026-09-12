"""8-bit OpenBundle CLI wordmark."""

from __future__ import annotations

import os
import sys

BANNER_RED = "\033[38;2;196;30;58m"
RESET = "\033[0m"

# Pixel-grid OPENBUNDLE (5 rows, 80-col safe).
WORDMARK = r"""
 ████  ████  ████ █  █ ████ █  █ █  █ ████ █    ████
█    █ █   █ █    ██ █ █  █ █  █ ██ █ █  █ █    █
█    █ ████  ████ █ ██ ████ █  █ █ ██ █  █ █    ████
█    █ █     █    █  █ █  █ █  █ █  █ █  █ █    █
 ████  █     ████ █  █ ████  ██  █  █ ████ ████ ████
""".strip("\n")

TAGLINE = "optimization proxy  ·  127.0.0.1:4180"


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def render_banner(*, color: bool | None = None) -> str:
    use_color = _color_enabled() if color is None else color
    if use_color:
        painted = "\n".join(f"{BANNER_RED}{line}{RESET}" for line in WORDMARK.splitlines())
        return f"{painted}\n{TAGLINE}"
    return f"{WORDMARK}\n{TAGLINE}"


def print_banner(*, no_banner: bool = False, compact: bool = False) -> None:
    if no_banner or os.environ.get("OPENBUNDLE_NO_BANNER"):
        return
    if compact:
        line = "OPENBUNDLE"
        if _color_enabled():
            print(f"{BANNER_RED}{line}{RESET}  {TAGLINE}", file=sys.stderr)
        else:
            print(f"{line}  {TAGLINE}", file=sys.stderr)
        return
    print(render_banner(), file=sys.stderr)

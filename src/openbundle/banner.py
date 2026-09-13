"""8-bit openbundle CLI wordmark — open in grey, bundle in white."""

from __future__ import annotations

import os
import sys

# Match openbundle-logo-horizontal-dark.svg
OPEN_GREY = "\033[38;2;139;138;146m"
BUNDLE_WHITE = "\033[38;2;246;245;242m"
RESET = "\033[0m"
BANNER_RED = OPEN_GREY  # leftover name; pulse bar uses grey now

# 5-row pixel glyphs, 5 cols each, all lowercase.
_GLYPHS: dict[str, tuple[str, ...]] = {
    "o": (
        " ███ ",
        "█   █",
        "█   █",
        "█   █",
        " ███ ",
    ),
    "p": (
        "████ ",
        "█   █",
        "████ ",
        "█    ",
        "█    ",
    ),
    "e": (
        "████ ",
        "█    ",
        "███  ",
        "█    ",
        "████ ",
    ),
    "n": (
        "█   █",
        "██  █",
        "█ █ █",
        "█  ██",
        "█   █",
    ),
    "b": (
        "█    ",
        "█    ",
        "████ ",
        "█   █",
        "████ ",
    ),
    "u": (
        "█   █",
        "█   █",
        "█   █",
        "█   █",
        " ███ ",
    ),
    "d": (
        "    █",
        "    █",
        " ████",
        "█   █",
        " ████",
    ),
    "l": (
        "█    ",
        "█    ",
        "█    ",
        "█    ",
        "████ ",
    ),
}

_GAP = "  "


def _compose(word: str) -> list[str]:
    rows = [""] * 5
    for i, ch in enumerate(word):
        glyph = _GLYPHS[ch]
        pad = " " if i else ""
        for r, piece in enumerate(glyph):
            rows[r] += pad + piece
    return rows


_OPEN_ROWS = _compose("open")
_BUNDLE_ROWS = _compose("bundle")
WORDMARK = "\n".join(left + _GAP + right for left, right in zip(_OPEN_ROWS, _BUNDLE_ROWS))

TAGLINE = "optimization proxy  ·  127.0.0.1:4180"


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty() or sys.stderr.isatty()


def paint_wordmark(*, color: bool | None = None) -> str:
    use_color = _color_enabled() if color is None else color
    if not use_color:
        return WORDMARK
    return "\n".join(
        f"{OPEN_GREY}{left}{RESET}{_GAP}{BUNDLE_WHITE}{right}{RESET}"
        for left, right in zip(_OPEN_ROWS, _BUNDLE_ROWS)
    )


def paint_compact(*, color: bool | None = None) -> str:
    use_color = _color_enabled() if color is None else color
    if not use_color:
        return "openbundle"
    return f"{OPEN_GREY}open{RESET}{BUNDLE_WHITE}bundle{RESET}"


def render_banner(*, color: bool | None = None) -> str:
    return f"{paint_wordmark(color=color)}\n{TAGLINE}"


def print_banner(*, no_banner: bool = False, compact: bool = False) -> None:
    if no_banner or os.environ.get("OPENBUNDLE_NO_BANNER"):
        return
    if compact:
        print(f"{paint_compact()}  {TAGLINE}", file=sys.stderr)
        return
    print(render_banner(), file=sys.stderr)

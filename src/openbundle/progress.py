"""Quiet progress: 8-bit logo plus a pulsing bar. No pip novels."""

from __future__ import annotations

import os
import sys
import threading

from openbundle.banner import OPEN_GREY, RESET, paint_wordmark

BAR_WIDTH = 28
_HIDE_CURSOR = "\033[?25l"
_SHOW_CURSOR = "\033[?25h"


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stderr.isatty()


def _paint(text: str) -> str:
    if _color_enabled():
        return f"{OPEN_GREY}{text}{RESET}"
    return text


def _wordmark() -> str:
    return paint_wordmark(color=_color_enabled())


def _bar(filled: int) -> str:
    filled = max(0, min(BAR_WIDTH, filled))
    return "[" + ("█" * filled) + ("░" * (BAR_WIDTH - filled)) + "]"


class Pulse:
    """Logo + pulsing bar while a long step runs (pip, etc.)."""

    def __init__(self, label: str, *, show_logo: bool = True) -> None:
        self.label = label
        self.show_logo = show_logo
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tty = sys.stderr.isatty() and not sys.stderr.closed

    def __enter__(self) -> Pulse:
        if not self._tty:
            print(f"{self.label}...", file=sys.stderr, flush=True)
            return self
        if self.show_logo:
            print(_wordmark(), file=sys.stderr)
        sys.stderr.write(_HIDE_CURSOR)
        sys.stderr.flush()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        pos = 0
        direction = 1
        while not self._stop.wait(0.08):
            pos += direction
            if pos >= BAR_WIDTH or pos <= 0:
                direction *= -1
                pos = max(0, min(BAR_WIDTH, pos))
            sys.stderr.write(f"\r{_paint(_bar(pos))}  {self.label}   ")
            sys.stderr.flush()

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._tty:
            done = "done" if exc_type is None else "failed"
            sys.stderr.write(f"\r{_paint(_bar(BAR_WIDTH))}  {self.label}  {done}{_SHOW_CURSOR}\n")
            sys.stderr.flush()


def step(label: str) -> None:
    if sys.stderr.isatty():
        print(f"{_paint('▸')} {label}", file=sys.stderr)
    else:
        print(label, file=sys.stderr)

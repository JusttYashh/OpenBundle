"""Repeated + long-context fixture for README-style reports."""

from __future__ import annotations

LONG = ("You are reviewing a large codebase. " * 80) + "What is the entrypoint?"
REPEATS = [
    "Summarize the previous answer in one sentence.",
    "Summarize the previous answer in one sentence.",
    "Explain HTTP caching.",
    "Explain HTTP caching.",
]


def prompts() -> list[str]:
    items = [LONG]
    items.extend(REPEATS)
    items.extend([f"unique turn {i}" for i in range(12)])
    return items


def openai_bodies() -> list[dict]:
    return [{"model": "gpt-4.1", "messages": [{"role": "user", "content": p}]} for p in prompts()]

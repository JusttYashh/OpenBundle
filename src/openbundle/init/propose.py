"""Recommended tools shown at init, with individual effects. Not an LLM."""

from __future__ import annotations

from dataclasses import dataclass

from openbundle.init.scan import ScanResult, installed_extras


@dataclass(frozen=True)
class Recommendation:
    id: str
    name: str
    extra: str | None
    effect: str
    caveat: str
    built_in: bool


RECOMMENDATIONS: tuple[Recommendation, ...] = (
    Recommendation(
        id="sqlite_exact",
        name="Exact-hash cache",
        extra=None,
        effect="Identical prompts skip the provider: lower latency and $0 for those hits.",
        caveat="No quality change. Only exact repeats; similar-but-different prompts still miss.",
        built_in=True,
    ),
    Recommendation(
        id="mem0",
        name="Mem0",
        extra="mem0",
        effect=(
            "Replaces stuffing full conversation history with retrieved memories. "
            "Published: ~90% lower token usage and ~91% faster vs full-context on Mem0's bench."
        ),
        caveat="Extraction uses its own LLM call; OpenBundle rate-limits it (every 3 turns / 15s / 4 per minute).",
        built_in=False,
    ),
    Recommendation(
        id="llmlingua2",
        name="LLMLingua-2",
        extra="llmlingua",
        effect=(
            "Compresses remaining prompt text by dropping low-information tokens. "
            "Published: up to 20x fewer prompt tokens on research benches (~5-10x on typical prompts)."
        ),
        caveat="Installs a small local model. Never rewrites tools or Anthropic cache_control blocks.",
        built_in=False,
    ),
)


def extras_to_install(installed: list[str] | None = None) -> list[str]:
    have = set(installed if installed is not None else installed_extras())
    needed: list[str] = []
    for rec in RECOMMENDATIONS:
        if rec.extra and rec.extra not in have:
            needed.append(rec.extra)
    return needed


def scan_summary(scan: ScanResult) -> str:
    profile = "coding-agent" if scan.coding_agent else "API app / SDK"
    hints = ", ".join(scan.hints) if scan.hints else "generic"
    keys = []
    if scan.anthropic_key:
        keys.append("Anthropic")
    if scan.openai_key:
        keys.append("OpenAI")
    key_s = ", ".join(keys) if keys else "none in env"
    return f"Detected: {profile} ({hints}). Provider keys: {key_s}."

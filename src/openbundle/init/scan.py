"""Environment scan for openbundle init."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field


@dataclass
class ScanResult:
    anthropic_key: bool = False
    openai_key: bool = False
    coding_agent: bool = False
    hints: list[str] = field(default_factory=list)


def _has_dist(name: str) -> bool:
    try:
        from importlib.metadata import PackageNotFoundError, version

        version(name)
        return True
    except PackageNotFoundError:
        return False
    except Exception:
        return False


def installed_extras() -> list[str]:
    """Detect extras via package metadata — do not import mem0/llmlingua (torch)."""
    extras: list[str] = []
    mapping = {
        "mem0ai": "mem0",
        "llmlingua": "llmlingua",
        "gptcache": "gptcache",
        "presidio-analyzer": "presidio",
        "semantic-router": "semantic_router",
        "lmcache": "lmcache",
    }
    for dist, extra in mapping.items():
        if _has_dist(dist):
            extras.append(extra)
    return extras


def scan_env() -> ScanResult:
    result = ScanResult()
    result.anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    result.openai_key = bool(os.environ.get("OPENAI_API_KEY"))
    if shutil.which("claude") or os.environ.get("CLAUDE_CODE") or os.environ.get("CLAUDECODE"):
        result.coding_agent = True
        result.hints.append("claude")
    if shutil.which("cursor") or os.environ.get("CURSOR_TRACE_ID"):
        result.coding_agent = True
        result.hints.append("cursor")
    if shutil.which("aider"):
        result.coding_agent = True
        result.hints.append("aider")
    if shutil.which("ollama"):
        result.hints.append("ollama")
    if shutil.which("vllm") or os.environ.get("VLLM_BASE_URL"):
        result.hints.append("vllm")
    if os.environ.get("SGLANG_BASE_URL"):
        result.hints.append("sglang")
    return result

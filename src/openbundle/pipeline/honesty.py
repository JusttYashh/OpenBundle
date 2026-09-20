"""Vendor names may only go LIVE when the stage was built from that library."""

from __future__ import annotations

from typing import Any

# Catalog tool_id → import/library tag the constructed stage must carry.
# First-party fallbacks (prefix_router, json_schema, regex scans, citation heuristic)
# are omitted: they must never be published under a vendor tool_id.
VENDOR_LIBRARIES: dict[str, str] = {
    "gptcache": "gptcache",
    "llmlingua2": "llmlingua",
    "llmlingua": "llmlingua",
    "selective_context": "selective_context",
    "recomp": "recomp",
    "llm_guard": "llm_guard",
    "presidio": "presidio",
    "rebuff": "rebuff",
    "nemo_guardrails": "nemoguardrails",
    "semantic_router": "semantic_router",
    "routellm": "routellm",
    "litellm": "litellm",
    "guardrails_ai": "guardrails",
    "instructor": "instructor",
    "promptfoo": "promptfoo",
    "deepeval": "deepeval",
    "opik": "opik",
    "lynx": "lynx",
    "langfuse": "langfuse",
    "openobserve": "openobserve",
    "openmeter": "openmeter",
    "agentops": "agentops",
    "agenta": "agenta",
    "lmcache": "lmcache",
    "kvcached": "kvcached",
    "kvzip": "kvzip",
    "deepspec": "deepspec",
}


def required_library(tool_id: str | None) -> str | None:
    if not tool_id:
        return None
    return VENDOR_LIBRARIES.get(tool_id)


def stage_library(stage: Any) -> str | None:
    value = getattr(stage, "library", None)
    if isinstance(value, str) and value:
        return value
    return None


def vendor_claim_ok(tool_id: str | None, stage: Any) -> bool:
    """False when a vendor tool_id is attached to a stage that is not that library."""
    needed = required_library(tool_id)
    if needed is None:
        return True
    if stage is None:
        return False
    return stage_library(stage) == needed

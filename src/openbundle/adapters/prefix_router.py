"""First-party prefix router: claude* → Anthropic, gpt/o* → OpenAI."""

from __future__ import annotations

import copy

from openbundle.config import RoutingLayerConfig
from openbundle.pipeline.types import InternalRequest


def _looks_anthropic(model: str) -> bool:
    lower = (model or "").lower()
    return lower.startswith("claude") or "anthropic" in lower


def _looks_openai(model: str) -> bool:
    lower = (model or "").lower()
    return (
        lower.startswith("gpt")
        or lower.startswith("o1")
        or lower.startswith("o3")
        or lower.startswith("o4")
        or "openai" in lower
    )


class PrefixRouter:
    name = "routing"

    def __init__(self, config: RoutingLayerConfig) -> None:
        self.config = config

    def apply(self, request: InternalRequest) -> InternalRequest:
        if not self.config.enabled:
            return request
        try:
            updated = copy.copy(request)
            if _looks_anthropic(request.model) and request.protocol != "anthropic":
                updated.protocol = "anthropic"
            elif _looks_openai(request.model) and request.protocol != "openai":
                updated.protocol = "openai"
            return updated
        except Exception:
            return request

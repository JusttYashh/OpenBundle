"""First-party input guardrails. Fail-open: never drop the request on error."""

from __future__ import annotations

import copy

from openbundle.config import GuardrailsLayerConfig
from openbundle.pipeline.types import InternalRequest

MAX_CHARS = 400_000


def _clip(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + "\n…[truncated by OpenBundle input guardrails]"


class InputGuard:
    name = "guardrails"

    def __init__(self, config: GuardrailsLayerConfig) -> None:
        self.config = config

    def apply(self, request: InternalRequest) -> InternalRequest:
        if not self.config.enabled:
            return request
        try:
            updated = copy.copy(request)
            messages = []
            for message in request.messages:
                item = dict(message)
                content = item.get("content")
                if isinstance(content, str):
                    item["content"] = _clip(content)
                messages.append(item)
            updated.messages = messages
            if isinstance(request.system, str):
                updated.system = _clip(request.system)
            return updated
        except Exception:
            return request

"""Message-level session hygiene. Dedup, trim stale tool output, sliding window."""

from __future__ import annotations

import copy
from typing import Any

from openbundle.config import ContextLayerConfig
from openbundle.pipeline.types import InternalRequest

TOOL_ROLES = {"tool", "function"}
MAX_TOOL_CHARS = 4_000


def _content_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    return str(content or "")


def _is_error_tool(message: dict[str, Any]) -> bool:
    text = _content_text(message).lower()
    if message.get("role") not in TOOL_ROLES:
        return False
    return "error" in text or "traceback" in text or text.startswith("failed")


def _trim_tool(message: dict[str, Any]) -> dict[str, Any]:
    if message.get("role") not in TOOL_ROLES:
        return message
    text = _content_text(message)
    if len(text) <= MAX_TOOL_CHARS:
        return message
    item = dict(message)
    item["content"] = text[:MAX_TOOL_CHARS] + "\n…[truncated stale tool output]"
    return item


class SessionHygiene:
    name = "context"

    def __init__(self, config: ContextLayerConfig) -> None:
        self.config = config

    def apply(self, request: InternalRequest) -> InternalRequest:
        if not self.config.enabled:
            return request
        try:
            messages = list(request.messages)
            seen: set[str] = set()
            cleaned: list[dict[str, Any]] = []
            for message in messages:
                role = str(message.get("role") or "")
                text = _content_text(message)
                key = f"{role}:{text}"
                if role in TOOL_ROLES and _is_error_tool(message):
                    continue
                if text and key in seen:
                    continue
                if text:
                    seen.add(key)
                cleaned.append(_trim_tool(message))
            window = self.config.window
            if window > 0 and len(cleaned) > window:
                cleaned = cleaned[-window:]
            updated = copy.copy(request)
            updated.messages = cleaned
            body = dict(request.body)
            body["messages"] = cleaned
            updated.body = body
            return updated
        except Exception:
            return request

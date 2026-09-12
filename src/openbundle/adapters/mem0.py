"""Sliding-window + extractive summary fallback; optional Mem0 extra."""

from __future__ import annotations

import copy
import time
from collections import deque
from typing import Any

from openbundle.config import MemoryLayerConfig
from openbundle.metrics.tokens import count_messages, count_text
from openbundle.pipeline.types import InternalRequest, InternalResponse


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content")
            return content if isinstance(content, str) else str(content or "")
    return ""


def _summarize(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message.get("role") or "user"
        content = message.get("content")
        text = content if isinstance(content, str) else str(content or "")
        first = text.strip().split("\n", 1)[0][:240]
        if first:
            lines.append(f"{role}: {first}")
    return "Prior context (compressed):\n" + "\n".join(lines)


class MemoryLayer:
    name = "memory"

    def __init__(self, config: MemoryLayerConfig) -> None:
        self.config = config
        self._turns = 0
        self._last_extract = 0.0
        self._extracts = deque()
        self._mem0 = None
        self._mem0_tried = False

    def _mem0_client(self) -> Any | None:
        if self._mem0 is not None:
            return self._mem0
        if self.config.adapter != "mem0" or not self.config.enabled:
            return None
        if not self._mem0_tried:
            self._mem0_tried = True
            self._mem0 = _try_mem0()
        return self._mem0

    def apply(self, request: InternalRequest) -> InternalRequest:
        if not self.config.enabled:
            return request
        try:
            if self._mem0_client() is not None:
                return self._apply_mem0(request)
            return self._apply_summary(request)
        except Exception:
            return request

    def _apply_summary(self, request: InternalRequest) -> InternalRequest:
        window = self.config.window
        messages = list(request.messages)
        if len(messages) <= window:
            return request
        dropped, kept = messages[:-window], messages[-window:]
        summary = {
            "role": "system" if request.protocol == "openai" else "user",
            "content": _summarize(dropped),
        }
        if request.protocol == "anthropic":
            # Anthropic system is separate; keep summary as a user preface.
            summary = {"role": "user", "content": _summarize(dropped)}
        new_messages = [summary] + kept
        updated = copy.copy(request)
        updated.messages = new_messages
        return updated

    def _apply_mem0(self, request: InternalRequest) -> InternalRequest:
        query = _last_user_text(request.original_messages)
        if not query:
            return request
        memories = self._mem0.search(query, user_id=self.config.user_id)  # type: ignore[union-attr]
        texts = _mem0_texts(memories)
        if not texts:
            return request
        blob = "Relevant memories:\n" + "\n".join(f"- {item}" for item in texts[:8])
        updated = copy.copy(request)
        if request.protocol == "anthropic":
            existing = request.system
            if existing is None:
                updated.system = blob
            elif isinstance(existing, str):
                updated.system = existing + "\n\n" + blob
            else:
                updated.system = existing
        else:
            updated.messages = [{"role": "system", "content": blob}] + list(request.messages)
        return updated

    def allow_extract(self, request: InternalRequest) -> bool:
        cfg = self.config.extract
        user_tokens = count_text(_last_user_text(request.original_messages))
        if user_tokens < cfg.skip_if_user_tokens_below:
            return False
        self._turns += 1
        now = time.time()
        while self._extracts and now - self._extracts[0] > 60:
            self._extracts.popleft()
        if self._turns % cfg.every_n_turns != 0:
            return False
        if now - self._last_extract < cfg.min_interval_seconds:
            return False
        if len(self._extracts) >= cfg.max_per_minute:
            return False
        return True

    def extract(self, request: InternalRequest, response: InternalResponse) -> int:
        if not self.config.enabled or not response.ok:
            return 0
        if not self.allow_extract(request):
            return 0
        # Always extract from ORIGINAL conversation, never compressed text.
        payload = request.original_messages
        tokens = count_messages(payload, request.system)
        try:
            client = self._mem0_client()
            if client is not None:
                client.add(payload, user_id=self.config.user_id)
        except Exception:
            return 0
        self._last_extract = time.time()
        self._extracts.append(self._last_extract)
        return tokens


def _try_mem0() -> Any | None:
    try:
        from mem0 import Memory  # type: ignore

        return Memory()
    except Exception:
        return None


def _mem0_texts(result: Any) -> list[str]:
    if result is None:
        return []
    if isinstance(result, dict):
        items = result.get("results") or result.get("memories") or []
        return [str(item.get("memory") or item.get("text") or item) for item in items]
    if isinstance(result, list):
        return [str(item) for item in result]
    return [str(result)]

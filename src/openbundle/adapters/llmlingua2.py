"""LLMLingua-2 adapter. Fail-open. Never rewrite tools or cache_control blocks."""

from __future__ import annotations

import copy
from typing import Any

from openbundle.config import CompressLayerConfig
from openbundle.pipeline.types import InternalRequest


def _has_cache_control(block: Any) -> bool:
    if isinstance(block, dict) and "cache_control" in block:
        return True
    if isinstance(block, list):
        return any(_has_cache_control(item) for item in block)
    return False


def _is_protected_message(message: dict[str, Any]) -> bool:
    content = message.get("content")
    if _has_cache_control(content) or _has_cache_control(message):
        return True
    if message.get("role") in {"tool", "function"}:
        return True
    return False


def _text_of(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    return None


class CompressLayer:
    name = "compress"

    def __init__(self, config: CompressLayerConfig) -> None:
        self.config = config
        self._compressor = None
        self._compressor_tried = False

    def _get_compressor(self) -> Any | None:
        if self._compressor is not None:
            return self._compressor
        if not self.config.enabled or self.config.adapter != "llmlingua2":
            return None
        if not self._compressor_tried:
            self._compressor_tried = True
            self._compressor = _try_llmlingua()
        return self._compressor

    def apply(self, request: InternalRequest) -> InternalRequest:
        if not self.config.enabled:
            return request
        if request.tools:
            # Do not rewrite tool schemas; still may compress unprotected text messages.
            pass
        try:
            return self._compress(request)
        except Exception:
            return request

    def _compress(self, request: InternalRequest) -> InternalRequest:
        compressor = self._get_compressor()
        if compressor is None:
            # Extra not installed — never silently heuristic-rewrite user prompts.
            return request
        updated = copy.copy(request)
        updated.messages = [self._compress_message(m, compressor) for m in request.messages]
        if request.system and not (self.config.skip_cache_control and _has_cache_control(request.system)):
            updated.system = self._compress_value(request.system, compressor)
        updated.body = dict(request.body)
        return updated

    def _compress_message(self, message: dict[str, Any], compressor: Any) -> dict[str, Any]:
        if self.config.skip_cache_control and _is_protected_message(message):
            return message
        text = _text_of(message.get("content"))
        if text is None:
            return message
        new_text = self._compress_text(text, compressor)
        out = dict(message)
        out["content"] = new_text
        return out

    def _compress_value(self, value: Any, compressor: Any) -> Any:
        text = _text_of(value)
        if text is None:
            return value
        return self._compress_text(text, compressor)

    def _compress_text(self, text: str, compressor: Any) -> str:
        rate = self.config.rate
        result = compressor.compress_prompt(text, rate=rate, force_tokens=["\n"])
        if isinstance(result, dict):
            return str(result.get("compressed_prompt") or result.get("compressed") or text)
        if isinstance(result, str):
            return result
        return text


def _try_llmlingua() -> Any | None:
    try:
        from llmlingua import PromptCompressor  # type: ignore

        return PromptCompressor()
    except Exception:
        return None

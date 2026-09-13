"""Inject provider-native prompt-cache breakpoints. Fail-open. Never double-wrap."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from openbundle.config import PromptCacheLayerConfig
from openbundle.pipeline.types import InternalRequest


def _has_cache_control(value: Any) -> bool:
    if isinstance(value, dict) and "cache_control" in value:
        return True
    if isinstance(value, list):
        return any(_has_cache_control(item) for item in value)
    return False


def _wrap_anthropic_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def _mark_system(system: Any) -> Any:
    if _has_cache_control(system):
        return system
    if isinstance(system, str) and system:
        return _wrap_anthropic_text(system)
    if isinstance(system, list):
        updated = []
        marked = False
        for i, block in enumerate(system):
            item = dict(block) if isinstance(block, dict) else block
            if isinstance(item, dict) and not marked and i == len(system) - 1:
                if "cache_control" not in item:
                    item = dict(item)
                    item["cache_control"] = {"type": "ephemeral"}
                marked = True
            updated.append(item)
        return updated
    return system


def _mark_tools(tools: list[Any]) -> list[Any]:
    if not tools or _has_cache_control(tools):
        return tools
    out = []
    for i, tool in enumerate(tools):
        item = dict(tool) if isinstance(tool, dict) else tool
        if isinstance(item, dict) and i == len(tools) - 1 and "cache_control" not in item:
            item = dict(item)
            item["cache_control"] = {"type": "ephemeral"}
        out.append(item)
    return out


def _prompt_cache_key(request: InternalRequest) -> str:
    blob = json.dumps(
        {"system": request.system, "tools": request.tools, "model": request.model},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class PromptCacheInject:
    name = "prompt_cache"

    def __init__(self, config: PromptCacheLayerConfig) -> None:
        self.config = config

    def apply(self, request: InternalRequest) -> InternalRequest:
        if not self.config.enabled:
            return request
        try:
            updated = copy.copy(request)
            body = dict(request.body)
            if request.protocol == "anthropic":
                if request.system is not None:
                    updated.system = _mark_system(request.system)
                    body["system"] = updated.system
                if request.tools:
                    updated.tools = _mark_tools(list(request.tools))
                    body["tools"] = updated.tools
            else:
                body.setdefault("prompt_cache_key", _prompt_cache_key(request))
            updated.body = body
            return updated
        except Exception:
            return request

"""Validate JSON-mode responses and retry once. Fail-open."""

from __future__ import annotations

import json
from typing import Any

from openbundle.config import StructuredLayerConfig
from openbundle.pipeline.types import InternalRequest, InternalResponse


def wants_json(request: InternalRequest) -> bool:
    fmt = request.body.get("response_format")
    if isinstance(fmt, dict) and fmt.get("type") in {"json_object", "json_schema"}:
        return True
    return False


def _assistant_text(response: InternalResponse, protocol: str) -> str:
    body = response.body or {}
    if protocol == "openai":
        choices = body.get("choices") or []
        if choices:
            return str((choices[0].get("message") or {}).get("content") or "")
    content = body.get("content")
    if isinstance(content, list) and content:
        return str(content[0].get("text") or "")
    return ""


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except Exception:
        return False


class JsonSchemaRetry:
    name = "structured"

    def __init__(self, config: StructuredLayerConfig) -> None:
        self.config = config

    def should_retry(self, request: InternalRequest, response: InternalResponse) -> bool:
        if not self.config.enabled or not response.ok or request.stream:
            return False
        if not wants_json(request):
            return False
        text = _assistant_text(response, request.protocol)
        if not text:
            return False
        return not _is_json(text)

    def retry_request(self, request: InternalRequest) -> InternalRequest:
        extra = {
            "role": "user",
            "content": "Your previous reply was not valid JSON. Reply with JSON only.",
        }
        updated = request
        try:
            import copy

            updated = copy.copy(request)
            updated.messages = list(request.messages) + [extra]
            body = dict(request.body)
            body["messages"] = updated.messages
            updated.body = body
        except Exception:
            return request
        return updated

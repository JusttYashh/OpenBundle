"""Anthropic Messages parsing."""

from __future__ import annotations

import copy
from typing import Any

from openbundle.pipeline.types import InternalRequest


def parse_anthropic(body: dict[str, Any], headers: dict[str, str]) -> InternalRequest:
    messages = list(body.get("messages") or [])
    return InternalRequest(
        protocol="anthropic",
        model=str(body.get("model") or ""),
        messages=copy.deepcopy(messages),
        original_messages=copy.deepcopy(messages),
        body=body,
        stream=bool(body.get("stream")),
        tools=list(body.get("tools") or []),
        system=body.get("system"),
        headers=headers,
    )

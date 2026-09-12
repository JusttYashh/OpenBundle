"""OpenAI Chat Completions parsing."""

from __future__ import annotations

import copy
from typing import Any

from openbundle.pipeline.types import InternalRequest


def parse_openai(body: dict[str, Any], headers: dict[str, str]) -> InternalRequest:
    messages = list(body.get("messages") or [])
    return InternalRequest(
        protocol="openai",
        model=str(body.get("model") or ""),
        messages=copy.deepcopy(messages),
        original_messages=copy.deepcopy(messages),
        body=body,
        stream=bool(body.get("stream")),
        tools=list(body.get("tools") or []),
        headers=headers,
    )

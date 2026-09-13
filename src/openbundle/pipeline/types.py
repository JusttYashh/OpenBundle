"""Shared request/response types for the optimization pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ProtocolName = Literal["openai", "anthropic"]


@dataclass
class SSEEvent:
    data: str
    event: str | None = None
    raw: str = ""

    def render(self) -> str:
        if self.raw:
            text = self.raw
            if not text.endswith("\n"):
                text += "\n"
            if not text.endswith("\n\n"):
                text += "\n"
            return text
        lines: list[str] = []
        if self.event:
            lines.append(f"event: {self.event}")
        for chunk in self.data.split("\n"):
            lines.append(f"data: {chunk}")
        return "\n".join(lines) + "\n\n"


@dataclass
class InternalRequest:
    protocol: ProtocolName
    model: str
    messages: list[dict[str, Any]]
    original_messages: list[dict[str, Any]]
    body: dict[str, Any]
    stream: bool = False
    tools: list[Any] = field(default_factory=list)
    system: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    passthrough: bool = False


@dataclass
class InternalResponse:
    ok: bool
    status_code: int = 200
    body: dict[str, Any] | None = None
    error_body: bytes = b""
    error_content_type: str = "application/json"
    events: list[SSEEvent] = field(default_factory=list)
    stream: bool = False
    cache_hit: bool = False
    prompt_tokens_before: int = 0
    prompt_tokens_after: int = 0
    completion_tokens: int = 0
    memory_extract_tokens: int = 0
    latency_ms: float = 0.0
    model: str = ""
    protocol: ProtocolName = "openai"
    passthrough_headers: dict[str, str] = field(default_factory=dict)
    layers: list[str] = field(default_factory=list)
    provider_error: bool = False
    client_cancelled: bool = False
    eval_status: str = ""
    eval_reason: str = ""

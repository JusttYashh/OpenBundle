from __future__ import annotations

import json
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


@dataclass
class MockState:
    status: int = 200
    body: dict = field(default_factory=dict)
    stream: bool = False
    drop_after_first_event: bool = False
    mid_stream_error: bool = False
    calls: list = field(default_factory=list)


def anthropic_message(text: str = "hello from mock") -> dict:
    return {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-6",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }


def openai_message(text: str = "hello from mock") -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "model": "gpt-4.1",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
    }


def anthropic_sse(text: str = "hello from mock") -> str:
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_mock",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-4-6",
                    "content": [],
                    "usage": {"input_tokens": 12, "output_tokens": 0},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 8},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    chunks = []
    for name, payload in events:
        chunks.append(f"event: {name}\ndata: {json.dumps(payload)}\n\n")
    return "".join(chunks)


def openai_sse(text: str = "hello from mock") -> str:
    first = {
        "id": "chatcmpl-mock",
        "object": "chat.completion.chunk",
        "model": "gpt-4.1",
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}],
    }
    done = {
        "id": "chatcmpl-mock",
        "object": "chat.completion.chunk",
        "model": "gpt-4.1",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return f"data: {json.dumps(first)}\n\ndata: {json.dumps(done)}\n\ndata: [DONE]\n\n"


def build_mock_provider(state: MockState | None = None) -> FastAPI:
    state = state or MockState()
    mock = FastAPI()
    mock.state.mock = state

    @mock.post("/v1/messages")
    async def messages(request: Request):
        body = await request.json()
        state.calls.append(("anthropic", body))
        if state.status >= 400:
            return JSONResponse(
                {"type": "error", "error": {"type": "rate_limit_error", "message": "nope"}},
                status_code=state.status,
                headers={"retry-after": "1"},
            )
        if body.get("stream") or state.stream:
            payload = anthropic_sse()
            if state.mid_stream_error:
                payload = (
                    payload.split("event: message_stop")[0]
                    + 'event: error\ndata: {"type":"error","error":{"type":"overloaded_error","message":"busy"}}\n\n'
                )

            async def gen():
                parts = payload.split("\n\n")
                for i, part in enumerate(parts):
                    if not part.strip():
                        continue
                    if state.drop_after_first_event and i >= 1:
                        raise RuntimeError("provider disconnect")
                    yield part + "\n\n"

            return StreamingResponse(gen(), media_type="text/event-stream")
        return JSONResponse(state.body or anthropic_message())

    @mock.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        state.calls.append(("openai", body))
        if state.status >= 400:
            return JSONResponse(
                {"error": {"message": "rate limited", "type": "rate_limit_error"}},
                status_code=state.status,
            )
        if body.get("stream") or state.stream:
            payload = openai_sse()
            if state.mid_stream_error:
                payload = (
                    'data: {"id":"x","object":"chat.completion.chunk","choices":[{"delta":{"content":"hi"}}]}\n\n'
                    'data: {"error":{"message":"overloaded","type":"error"},"object":"error"}\n\n'
                )

            async def gen():
                parts = payload.split("\n\n")
                for i, part in enumerate(parts):
                    if not part.strip():
                        continue
                    if state.drop_after_first_event and i >= 1:
                        raise RuntimeError("provider disconnect")
                    yield part + "\n\n"

            return StreamingResponse(gen(), media_type="text/event-stream")
        return JSONResponse(state.body or openai_message())

    return mock

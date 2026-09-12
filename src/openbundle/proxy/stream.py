"""Parse and replay SSE for OpenAI and Anthropic."""

from __future__ import annotations

import json
from typing import Any, Iterable

from openbundle.pipeline.types import InternalResponse, ProtocolName, SSEEvent


def parse_sse_chunk(buffer: str) -> tuple[list[SSEEvent], str]:
    events: list[SSEEvent] = []
    while "\n\n" in buffer:
        raw, buffer = buffer.split("\n\n", 1)
        raw = raw.strip("\n")
        if not raw.strip() or raw.strip().startswith(":"):
            continue
        event_name = None
        data_lines: list[str] = []
        for line in raw.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        data = "\n".join(data_lines)
        events.append(SSEEvent(data=data, event=event_name, raw=raw + "\n\n"))
    return events, buffer


def render_events(events: Iterable[SSEEvent]) -> str:
    return "".join(event.render() for event in events)


def synthesize_events(response: InternalResponse) -> list[SSEEvent]:
    if response.events:
        return list(response.events)
    if response.protocol == "anthropic":
        return _synth_anthropic(response.body or {})
    return _synth_openai(response.body or {}, response.model)


def _synth_openai(body: dict[str, Any], model: str) -> list[SSEEvent]:
    choice = ((body.get("choices") or [{}])[0]) or {}
    message = choice.get("message") or {}
    content = message.get("content") or ""
    finish = choice.get("finish_reason") or "stop"
    cid = body.get("id") or "openbundle-cache"
    events: list[SSEEvent] = []
    if content:
        chunk = {
            "id": cid,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}],
        }
        events.append(SSEEvent(data=json.dumps(chunk)))
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        chunk = {
            "id": cid,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "delta": {"tool_calls": tool_calls}, "finish_reason": None}],
        }
        events.append(SSEEvent(data=json.dumps(chunk)))
    done = {
        "id": cid,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
    }
    events.append(SSEEvent(data=json.dumps(done)))
    events.append(SSEEvent(data="[DONE]"))
    return events


def _synth_anthropic(body: dict[str, Any]) -> list[SSEEvent]:
    message_id = body.get("id") or "openbundle-cache"
    model = body.get("model") or ""
    content = body.get("content") or []
    usage = body.get("usage") or {}
    events = [
        SSEEvent(
            event="message_start",
            data=json.dumps(
                {
                    "type": "message_start",
                    "message": {
                        "id": message_id,
                        "type": "message",
                        "role": "assistant",
                        "model": model,
                        "content": [],
                        "stop_reason": None,
                        "usage": {"input_tokens": usage.get("input_tokens", 0), "output_tokens": 0},
                    },
                }
            ),
        )
    ]
    for index, block in enumerate(content):
        btype = block.get("type") or "text"
        events.append(
            SSEEvent(
                event="content_block_start",
                data=json.dumps(
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": _start_block(block, btype),
                    }
                ),
            )
        )
        if btype == "text":
            events.append(
                SSEEvent(
                    event="content_block_delta",
                    data=json.dumps(
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {"type": "text_delta", "text": block.get("text") or ""},
                        }
                    ),
                )
            )
        elif btype == "tool_use":
            events.append(
                SSEEvent(
                    event="content_block_delta",
                    data=json.dumps(
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": json.dumps(block.get("input") or {}),
                            },
                        }
                    ),
                )
            )
        events.append(
            SSEEvent(
                event="content_block_stop",
                data=json.dumps({"type": "content_block_stop", "index": index}),
            )
        )
    events.append(
        SSEEvent(
            event="message_delta",
            data=json.dumps(
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": body.get("stop_reason") or "end_turn"},
                    "usage": {"output_tokens": usage.get("output_tokens", 0)},
                }
            ),
        )
    )
    events.append(SSEEvent(event="message_stop", data=json.dumps({"type": "message_stop"})))
    return events


def _start_block(block: dict[str, Any], btype: str) -> dict[str, Any]:
    if btype == "tool_use":
        return {"type": "tool_use", "id": block.get("id"), "name": block.get("name"), "input": {}}
    if btype == "thinking":
        return {"type": "thinking", "thinking": ""}
    return {"type": "text", "text": ""}


def assemble_from_events(protocol: ProtocolName, events: list[SSEEvent], model: str) -> dict[str, Any]:
    if protocol == "anthropic":
        return _assemble_anthropic(events, model)
    return _assemble_openai(events, model)


def _assemble_openai(events: list[SSEEvent], model: str) -> dict[str, Any]:
    content = ""
    tool_calls: list[Any] = []
    finish = "stop"
    cid = "openbundle"
    for event in events:
        if event.data.strip() == "[DONE]":
            continue
        try:
            payload = json.loads(event.data)
        except json.JSONDecodeError:
            continue
        cid = payload.get("id") or cid
        choice = ((payload.get("choices") or [{}])[0]) or {}
        delta = choice.get("delta") or {}
        if delta.get("content"):
            content += delta["content"]
        if delta.get("tool_calls"):
            tool_calls.extend(delta["tool_calls"])
        if choice.get("finish_reason"):
            finish = choice["finish_reason"]
    message: dict[str, Any] = {"role": "assistant", "content": content or None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": cid,
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _assemble_anthropic(events: list[SSEEvent], model: str) -> dict[str, Any]:
    message: dict[str, Any] = {
        "id": "openbundle",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
    blocks: dict[int, dict[str, Any]] = {}
    for event in events:
        try:
            payload = json.loads(event.data) if event.data else {}
        except json.JSONDecodeError:
            continue
        etype = payload.get("type") or event.event
        if etype == "message_start":
            started = payload.get("message") or {}
            message.update({k: started[k] for k in ("id", "model", "role") if k in started})
            if "usage" in started:
                message["usage"] = started["usage"]
        elif etype == "content_block_start":
            index = int(payload.get("index") or 0)
            blocks[index] = dict(payload.get("content_block") or {"type": "text", "text": ""})
        elif etype == "content_block_delta":
            index = int(payload.get("index") or 0)
            delta = payload.get("delta") or {}
            block = blocks.setdefault(index, {"type": "text", "text": ""})
            if delta.get("type") == "text_delta":
                block["text"] = (block.get("text") or "") + (delta.get("text") or "")
            elif delta.get("type") == "input_json_delta":
                block["_json"] = (block.get("_json") or "") + (delta.get("partial_json") or "")
        elif etype == "message_delta":
            delta = payload.get("delta") or {}
            if delta.get("stop_reason"):
                message["stop_reason"] = delta["stop_reason"]
            if payload.get("usage"):
                message["usage"] = {**(message.get("usage") or {}), **payload["usage"]}
    assembled = []
    for index in sorted(blocks):
        block = blocks[index]
        if "_json" in block:
            try:
                block["input"] = json.loads(block.pop("_json") or "{}")
            except json.JSONDecodeError:
                block["input"] = {}
        assembled.append(block)
    message["content"] = assembled
    return message

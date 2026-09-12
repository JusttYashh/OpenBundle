"""Token counting (tiktoken estimates for both protocols)."""

from __future__ import annotations

from typing import Any

import tiktoken

_ENC = tiktoken.get_encoding("cl100k_base")


def count_text(text: str) -> int:
    if not text:
        return 0
    return len(_ENC.encode(text))


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if "text" in block:
                    parts.append(str(block.get("text") or ""))
                elif block.get("type") == "tool_use":
                    parts.append(str(block.get("name") or ""))
                elif "content" in block:
                    parts.append(_content_to_text(block["content"]))
        return "\n".join(parts)
    if isinstance(content, dict):
        return _content_to_text(content.get("text") or content.get("content") or "")
    return str(content)


def count_messages(messages: list[dict[str, Any]], system: Any = None) -> int:
    total = count_text(_content_to_text(system))
    for message in messages:
        total += count_text(str(message.get("role") or ""))
        total += count_text(_content_to_text(message.get("content")))
    return total

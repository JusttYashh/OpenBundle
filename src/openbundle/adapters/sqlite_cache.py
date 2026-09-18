"""SQLite exact-hash cache; embedding similarity is opt-in only."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from openbundle.pipeline.types import InternalRequest, InternalResponse, SSEEvent


def canonical_messages(messages: list[dict[str, Any]], extra: Any = None) -> str:
    payload = {"messages": messages, "extra": extra}
    return json.dumps(payload, sort_keys=True, default=str)


def exact_key(request: InternalRequest) -> str:
    blob = canonical_messages(
        request.original_messages,
        extra={"model": request.model, "tools": request.tools, "system": request.system},
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _tokenize(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in text.lower().split():
        counts[token] = counts.get(token, 0) + 1
    return counts


def _cosine(a: dict[str, int], b: dict[str, int]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def messages_text(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        else:
            parts.append(json.dumps(content, default=str))
    return "\n".join(parts)


class SqliteCache:
    def __init__(self, path: Path, *, semantic: bool = False, threshold: float = 0.95) -> None:
        self.path = path
        self.semantic = semantic
        self.threshold = threshold
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                model TEXT,
                text TEXT,
                payload TEXT NOT NULL,
                created REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, key: str) -> InternalResponse | None:
        row = self._conn.execute("SELECT payload FROM cache WHERE key = ?", (key,)).fetchone()
        if row:
            return _decode(row[0])
        return None

    def get_semantic(self, request: InternalRequest) -> InternalResponse | None:
        if not self.semantic:
            return None
        query = _tokenize(messages_text(request.original_messages))
        rows = self._conn.execute("SELECT text, payload FROM cache WHERE model = ?", (request.model,)).fetchall()
        best: tuple[float, str] | None = None
        for text, payload in rows:
            score = _cosine(query, _tokenize(text or ""))
            if score >= self.threshold and (best is None or score > best[0]):
                best = (score, payload)
        if best:
            return _decode(best[1])
        return None

    def put(self, key: str, request: InternalRequest, response: InternalResponse) -> None:
        if not response.ok or response.provider_error or response.client_cancelled:
            return
        payload = _encode(response)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO cache(key, model, text, payload, created)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                key,
                request.model,
                messages_text(request.original_messages),
                payload,
                time.time(),
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _encode(response: InternalResponse) -> str:
    return json.dumps(
        {
            "ok": response.ok,
            "status_code": response.status_code,
            "body": response.body,
            "events": [
                {"data": event.data, "event": event.event, "raw": event.raw}
                for event in response.events
            ],
            "prompt_tokens_before": response.prompt_tokens_before,
            "prompt_tokens_after": response.prompt_tokens_after,
            "completion_tokens": response.completion_tokens,
            "model": response.model,
            "protocol": response.protocol,
        }
    )


def _decode(payload: str) -> InternalResponse:
    data = json.loads(payload)
    events = [
        SSEEvent(data=item.get("data") or "", event=item.get("event"), raw=item.get("raw") or "")
        for item in data.get("events") or []
    ]
    return InternalResponse(
        ok=True,
        status_code=int(data.get("status_code") or 200),
        body=data.get("body"),
        events=events,
        cache_hit=True,
        prompt_tokens_before=int(data.get("prompt_tokens_before") or 0),
        prompt_tokens_after=0,
        completion_tokens=int(data.get("completion_tokens") or 0),
        model=str(data.get("model") or ""),
        protocol=data.get("protocol") or "openai",
        layers=["exact_hash"],
    )

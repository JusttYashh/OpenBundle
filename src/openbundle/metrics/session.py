"""JSONL session log under ~/.openbundle/sessions/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openbundle.config import Settings
from openbundle.pipeline.types import InternalResponse


class SessionLog:
    def __init__(self, settings: Settings, session_id: str | None = None) -> None:
        self.settings = settings
        self.dir = settings.session_path()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.path = self.dir / f"{self.session_id}.jsonl"

    def record(self, response: InternalResponse, extra: dict[str, Any] | None = None) -> None:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session": self.session_id,
            "protocol": response.protocol,
            "model": response.model,
            "ok": response.ok,
            "status": response.status_code,
            "cache": "hit" if response.cache_hit else "miss",
            "stream": response.stream,
            "prompt_tokens_before": response.prompt_tokens_before,
            "prompt_tokens_after": 0 if response.cache_hit else response.prompt_tokens_after,
            "completion_tokens": 0 if response.cache_hit else response.completion_tokens,
            "memory_extract_tokens": response.memory_extract_tokens,
            "latency_ms": round(response.latency_ms, 2),
            "layers": response.layers,
            "provider_error": response.provider_error,
            "client_cancelled": response.client_cancelled,
        }
        if extra:
            event.update(extra)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    @staticmethod
    def latest(directory: Path) -> Path | None:
        files = sorted(directory.glob("*.jsonl"))
        return files[-1] if files else None

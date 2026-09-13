"""Local-only request samples for smoke-check. Never transmitted."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openbundle import config as obconfig
from openbundle.pipeline.types import InternalRequest

MAX_SAMPLES = 40
MAX_CONTENT_CHARS = 4000


def samples_path() -> Path:
    return obconfig.state_dir() / "samples.jsonl"


def sampling_enabled() -> bool:
    import os

    return os.environ.get("OPENBUNDLE_NO_SAMPLES", "").strip() not in {"1", "true", "TRUE", "yes"}


def has_samples() -> bool:
    path = samples_path()
    return path.is_file() and path.stat().st_size > 0


def record_sample(request: InternalRequest) -> None:
    if not sampling_enabled() or request.passthrough:
        return
    path = samples_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "protocol": request.protocol,
        "model": request.model,
        "messages": _trim_messages(request.original_messages),
        "system": _trim_value(request.system),
    }
    existing = _read_all(path)
    existing.append(row)
    existing = existing[-MAX_SAMPLES:]
    path.write_text("".join(json.dumps(item) + "\n" for item in existing), encoding="utf-8")


def load_samples(limit: int = 8) -> list[dict[str, Any]]:
    return _read_all(samples_path())[-limit:]


def _read_all(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _trim_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_CONTENT_CHARS:
        return value[:MAX_CONTENT_CHARS]
    return value


def _trim_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for message in messages[-12:]:
        item = dict(message)
        content = item.get("content")
        item["content"] = _trim_value(content)
        out.append(item)
    return out

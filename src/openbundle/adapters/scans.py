"""Fail-open input scans. Vendor scanners only when the named library constructed."""

from __future__ import annotations

import copy
import re
from typing import Any, Callable

from openbundle.pipeline.types import InternalRequest

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
)

_INJECTION_HINTS = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard your system prompt",
    "you are now jailbroken",
    "dan mode",
    "developer mode enabled",
)


def _map_text(request: InternalRequest, fn: Callable[[str], str]) -> InternalRequest:
    updated = copy.copy(request)
    messages = []
    for message in request.messages:
        item = dict(message)
        content = item.get("content")
        if isinstance(content, str):
            item["content"] = fn(content)
        messages.append(item)
    updated.messages = messages
    if isinstance(request.system, str):
        updated.system = fn(request.system)
    return updated


class SecretsScan:
    """First-party regex redaction. Must not be published as LLM Guard."""

    job_id = "secrets"
    name = "secrets"
    library: str | None = None

    def apply(self, request: InternalRequest) -> InternalRequest:
        def redact(text: str) -> str:
            out = text
            for pattern in _SECRET_PATTERNS:
                out = pattern.sub("[REDACTED_SECRET]", out)
            return out

        return _map_text(request, redact)


class LlmGuardSecrets:
    job_id = "secrets"
    name = "secrets"
    library = "llm_guard"

    def __init__(self, scanner: Any) -> None:
        self._scanner = scanner

    def apply(self, request: InternalRequest) -> InternalRequest:
        def redact(text: str) -> str:
            result = self._scanner.scan(text)
            if isinstance(result, tuple) and result:
                return str(result[0])
            if isinstance(result, str):
                return result
            return text

        return _map_text(request, redact)


class InjectionScan:
    """First-party keyword flag. Must not be published as Rebuff."""

    job_id = "injection"
    name = "injection"
    library: str | None = None

    def apply(self, request: InternalRequest) -> InternalRequest:
        def mark(text: str) -> str:
            lower = text.lower()
            if any(hint in lower for hint in _INJECTION_HINTS):
                return "[injection_flag] " + text
            return text

        return _map_text(request, mark)


class RebuffScan:
    job_id = "injection"
    name = "injection"
    library = "rebuff"

    def __init__(self, client: Any) -> None:
        self._client = client

    def apply(self, request: InternalRequest) -> InternalRequest:
        def mark(text: str) -> str:
            detect = getattr(self._client, "detect_injection", None) or getattr(
                self._client, "is_injection", None
            )
            if detect is None:
                return text
            try:
                flagged = detect(text)
            except TypeError:
                flagged = detect(user_input=text)
            if flagged:
                return "[injection_flag] " + text
            return text

        return _map_text(request, mark)


class PiiScan:
    job_id = "pii"
    name = "pii"
    library: str | None = None

    def __init__(self, analyzer: Any | None = None) -> None:
        self._analyzer = analyzer
        if analyzer is not None:
            self.library = "presidio"

    def apply(self, request: InternalRequest) -> InternalRequest:
        analyzer = self._analyzer
        if analyzer is None:
            return request

        def redact(text: str) -> str:
            results = analyzer.analyze(text=text, language="en")
            if not results:
                return text
            out = text
            for hit in sorted(results, key=lambda item: getattr(item, "start", 0), reverse=True):
                start = int(getattr(hit, "start", 0))
                end = int(getattr(hit, "end", 0))
                out = out[:start] + "[REDACTED_PII]" + out[end:]
            return out

        return _map_text(request, redact)


def try_presidio() -> PiiScan | None:
    try:
        from presidio_analyzer import AnalyzerEngine  # type: ignore

        return PiiScan(AnalyzerEngine())
    except Exception:
        return None

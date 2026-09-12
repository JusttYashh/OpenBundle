"""Layer protocol."""

from __future__ import annotations

from typing import Protocol

from openbundle.pipeline.types import InternalRequest, InternalResponse


class Layer(Protocol):
    name: str

    def apply(self, request: InternalRequest) -> InternalRequest:
        ...


class CacheStore(Protocol):
    def get(self, key: str) -> InternalResponse | None:
        ...

    def put(self, key: str, response: InternalResponse) -> None:
        ...

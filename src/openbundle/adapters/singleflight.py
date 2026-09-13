"""First-party exact-hash single-flight. One provider call per in-flight key."""

from __future__ import annotations

import asyncio
from copy import deepcopy

from openbundle.adapters.sqlite_cache import exact_key
from openbundle.config import CoalesceLayerConfig
from openbundle.pipeline.types import InternalRequest, InternalResponse


class SingleFlight:
    name = "coalesce"

    def __init__(self, config: CoalesceLayerConfig) -> None:
        self.config = config
        self._inflight: dict[str, asyncio.Future[InternalResponse]] = {}
        self._lock = asyncio.Lock()

    async def join(self, request: InternalRequest) -> tuple[InternalResponse | None, bool]:
        """Return (shared_response, is_owner). Owner must call finish()."""
        if not self.config.enabled:
            return None, True
        try:
            key = exact_key(request)
            async with self._lock:
                existing = self._inflight.get(key)
                if existing is None:
                    loop = asyncio.get_running_loop()
                    fut: asyncio.Future[InternalResponse] = loop.create_future()
                    self._inflight[key] = fut
                    return None, True
            shared = await existing
            return deepcopy(shared), False
        except Exception:
            return None, True

    def finish(self, request: InternalRequest, result: InternalResponse) -> None:
        if not self.config.enabled:
            return
        try:
            key = exact_key(request)
            fut = self._inflight.pop(key, None)
            if fut is not None and not fut.done():
                fut.set_result(result)
        except Exception:
            return

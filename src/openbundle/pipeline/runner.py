"""Ordered pipeline: cache → memory → compress → provider."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from openbundle.adapters.llmlingua2 import CompressLayer
from openbundle.adapters.mem0 import MemoryLayer
from openbundle.config import Settings, overlay_enabled
from openbundle.metrics.tokens import count_messages
from openbundle.pipeline.layers.cache import CacheLayer
from openbundle.pipeline.types import InternalRequest, InternalResponse
from openbundle.proxy.forward import ProviderForwarder, iter_sse
from openbundle.proxy.stream import synthesize_events


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        cache: CacheLayer | None = None,
        memory: MemoryLayer | None = None,
        compress: CompressLayer | None = None,
        forwarder: ProviderForwarder | None = None,
    ) -> None:
        self.settings = settings
        self.cache = cache or CacheLayer(settings)
        self.memory = memory or MemoryLayer(settings.layers.memory)
        self.compress = compress or CompressLayer(settings.layers.compress)
        self.forwarder = forwarder or ProviderForwarder(settings)

    def _layers_active(self) -> list[str]:
        names: list[str] = []
        if self.settings.layers.cache.enabled:
            names.append("cache")
        if self.settings.layers.memory.enabled:
            names.append("memory")
        if self.settings.layers.compress.enabled:
            names.append("compress")
        return names or ["passthrough"]

    def prepare(
        self, request: InternalRequest
    ) -> tuple[InternalRequest, int, InternalResponse | None]:
        before = count_messages(request.original_messages, request.system)
        if request.passthrough or self.settings.passthrough or not overlay_enabled(self.settings):
            request.passthrough = True
            return request, before, None
        hit = self.cache.lookup(request)
        if hit:
            hit.prompt_tokens_before = before
            hit.prompt_tokens_after = 0
            hit.stream = request.stream
            hit.protocol = request.protocol
            hit.model = request.model or hit.model
            hit.layers = ["cache"]
            hit.cache_hit = True
            hit.events = synthesize_events(hit)
            return request, before, hit
        working = self.memory.apply(request)
        working = self.compress.apply(working)
        return working, before, None

    def finalize(
        self,
        request: InternalRequest,
        working: InternalRequest,
        before: int,
        result: InternalResponse,
        started: float,
    ) -> InternalResponse:
        result.prompt_tokens_before = before
        result.prompt_tokens_after = count_messages(working.messages, working.system)
        if result.cache_hit:
            result.prompt_tokens_after = 0
        result.latency_ms = (time.perf_counter() - started) * 1000
        result.layers = ["cache"] if result.cache_hit else self._layers_active()
        result.model = request.model
        result.protocol = request.protocol
        if result.ok and not result.provider_error and not request.passthrough and not result.cache_hit:
            self.cache.store_response(request, result)
            result.memory_extract_tokens = self.memory.extract(request, result)
        return result

    async def run(self, request: InternalRequest) -> InternalResponse:
        started = time.perf_counter()
        working, before, hit = self.prepare(request)
        if hit:
            return self.finalize(request, working, before, hit, started)
        result = await self.forwarder.forward(working)
        result.stream = request.stream
        return self.finalize(request, working, before, result, started)

    async def stream(self, request: InternalRequest) -> tuple[InternalResponse | None, AsyncIterator[bytes]]:
        """Prepare, then return (cache_hit_response_or_None, byte iterator).

        The iterator yields SSE bytes and records the final result on
        ``iterator.final`` after completion.
        """
        started = time.perf_counter()
        working, before, hit = self.prepare(request)
        if hit:
            finalized = self.finalize(request, working, before, hit, started)

            async def replay() -> AsyncIterator[bytes]:
                async for chunk in iter_sse(finalized):
                    yield chunk
                replay.final = finalized  # type: ignore[attr-defined]

            it = replay()
            it.final = finalized  # type: ignore[attr-defined]
            return finalized, it

        async def live() -> AsyncIterator[bytes]:
            result: InternalResponse | None = None
            async for kind, payload in self.forwarder.live_stream(working):
                if kind == "chunk":
                    yield payload  # type: ignore[misc]
                else:
                    result = payload  # type: ignore[assignment]
            if result is None:
                result = InternalResponse(
                    ok=False,
                    provider_error=True,
                    stream=True,
                    model=request.model,
                    protocol=request.protocol,
                )
            result.stream = True
            live.final = self.finalize(request, working, before, result, started)  # type: ignore[attr-defined]

        iterator = live()
        iterator.final = None  # type: ignore[attr-defined]
        return None, iterator

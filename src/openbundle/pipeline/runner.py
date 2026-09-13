"""Pipeline: cache → coalesce → memory → hygiene → compress → prompt-cache → route → guard → provider."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from openbundle.adapters.input_guard import InputGuard
from openbundle.adapters.json_schema import JsonSchemaRetry
from openbundle.adapters.llmlingua2 import CompressLayer
from openbundle.adapters.mem0 import MemoryLayer
from openbundle.adapters.prefix_router import PrefixRouter
from openbundle.adapters.prompt_cache import PromptCacheInject
from openbundle.adapters.sample_eval import SampleEval
from openbundle.adapters.session_hygiene import SessionHygiene
from openbundle.adapters.singleflight import SingleFlight
from openbundle.config import Settings, overlay_enabled
from openbundle.metrics.tokens import count_messages
from openbundle.pipeline.layers.cache import CacheLayer
from openbundle.pipeline.types import InternalRequest, InternalResponse
from openbundle.proxy.forward import ProviderForwarder, iter_sse
from openbundle.proxy.stream import synthesize_events

_WRAP_FLAGS = (
    ("cache", "cache"),
    ("coalesce", "coalesce"),
    ("memory", "memory"),
    ("context", "context"),
    ("compress", "compress"),
    ("prompt_cache", "prompt_cache"),
    ("routing", "routing"),
    ("guardrails", "guardrails"),
    ("structured", "structured"),
    ("eval", "eval"),
)


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        cache: CacheLayer | None = None,
        memory: MemoryLayer | None = None,
        context: SessionHygiene | None = None,
        compress: CompressLayer | None = None,
        prompt_cache: PromptCacheInject | None = None,
        routing: PrefixRouter | None = None,
        guardrails: InputGuard | None = None,
        structured: JsonSchemaRetry | None = None,
        eval_layer: SampleEval | None = None,
        coalesce: SingleFlight | None = None,
        forwarder: ProviderForwarder | None = None,
    ) -> None:
        self.settings = settings
        self.cache = cache or CacheLayer(settings)
        self.memory = memory or MemoryLayer(settings.layers.memory)
        self.context = context or SessionHygiene(settings.layers.context)
        self.compress = compress or CompressLayer(settings.layers.compress)
        self.prompt_cache = prompt_cache or PromptCacheInject(settings.layers.prompt_cache)
        self.routing = routing or PrefixRouter(settings.layers.routing)
        self.guardrails = guardrails or InputGuard(settings.layers.guardrails)
        self.structured = structured or JsonSchemaRetry(settings.layers.structured)
        self.eval_layer = eval_layer or SampleEval(settings.layers.eval)
        self.coalesce = coalesce or SingleFlight(settings.layers.coalesce)
        self.forwarder = forwarder or ProviderForwarder(settings)

    def _layers_active(self) -> list[str]:
        names: list[str] = []
        for attr, name in _WRAP_FLAGS:
            layer = getattr(self.settings.layers, attr, None)
            if layer is not None and getattr(layer, "enabled", False):
                names.append(name)
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
        working = self.context.apply(working)
        working = self.compress.apply(working)
        working = self.prompt_cache.apply(working)
        working = self.routing.apply(working)
        working = self.guardrails.apply(working)
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
            try:
                result.memory_extract_tokens = self.memory.extract(request, result)
            except Exception:
                result.memory_extract_tokens = 0
        extra = self.eval_layer.score(result)
        result.eval_status = extra.get("eval", "")
        result.eval_reason = extra.get("eval_reason", "")
        return result

    async def run(self, request: InternalRequest) -> InternalResponse:
        started = time.perf_counter()
        working, before, hit = self.prepare(request)
        if hit:
            return self.finalize(request, working, before, hit, started)
        shared, owner = await self.coalesce.join(request)
        if shared is not None and not owner:
            extra = list(shared.layers)
            if "coalesce" not in extra:
                extra.append("coalesce")
            shared.layers = extra
            return self.finalize(request, working, before, shared, started)
        finalized = InternalResponse(ok=False, provider_error=True)
        try:
            result = await self.forwarder.forward(working)
            if self.structured.should_retry(working, result):
                retry_req = self.structured.retry_request(working)
                result = await self.forwarder.forward(retry_req)
            result.stream = request.stream
            finalized = self.finalize(request, working, before, result, started)
            return finalized
        finally:
            if owner:
                self.coalesce.finish(request, finalized)

    async def stream(self, request: InternalRequest) -> tuple[InternalResponse | None, AsyncIterator[bytes]]:
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

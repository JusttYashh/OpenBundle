"""Pipeline: exact-hash → semantic → compress → history/RAG → scans → route → LiteLLM → provider → validate → eval/obs.

Memory is never in prepare(). Tier B stages are snapshotted at request start.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from openbundle.adapters.json_schema import JsonSchemaRetry
from openbundle.adapters.named import FaithfulnessHeuristic, ObsSink, SampledEval, SemanticCacheStage
from openbundle.adapters.nemo_rails import NemoRails
from openbundle.config import Settings, overlay_enabled
from openbundle.metrics.tokens import count_messages
from openbundle.pipeline.bootstrap import bootstrap_registry
from openbundle.pipeline.jobs import (
    AFTER_JOB_IDS,
    DEGRADED,
    LIVE,
    PREPARE_JOB_IDS,
    SCAN_JOB_IDS,
)
from openbundle.pipeline.layers.cache import CacheLayer
from openbundle.pipeline.registry import StageRegistry
from openbundle.pipeline.types import InternalRequest, InternalResponse
from openbundle.proxy.forward import ProviderForwarder, iter_sse
from openbundle.proxy.stream import synthesize_events


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        cache: CacheLayer | None = None,
        forwarder: ProviderForwarder | None = None,
        registry: StageRegistry | None = None,
        warm: bool = True,
        **_ignored: Any,
    ) -> None:
        self.settings = settings
        self.registry = registry or bootstrap_registry(settings, warm=warm)
        if cache is not None:
            self.registry.publish("exact_hash", cache, LIVE)
        self.forwarder = forwarder or ProviderForwarder(settings)

    @property
    def cache(self) -> CacheLayer | None:
        stage = self.registry.snapshot().get("exact_hash")
        return stage if isinstance(stage, CacheLayer) else None

    def _layers_active(self) -> list[str]:
        names = self.registry.live_jobs()
        return names or ["passthrough"]

    def _call_apply(
        self,
        job_id: str,
        stage: Any,
        request: InternalRequest,
        fail_open: list[str],
    ) -> InternalRequest:
        apply = getattr(stage, "apply", None)
        if apply is None:
            return request
        info = self.registry.get_info(job_id)
        if info.hard_down:
            return request
        try:
            out = apply(request)
            if info.state == DEGRADED:
                self.registry.recover(job_id)
            return out
        except Exception as exc:
            if job_id in SCAN_JOB_IDS or True:
                self.registry.fail_open(job_id, exc)
                fail_open.append(job_id)
                return request
            raise

    def prepare(
        self, request: InternalRequest
    ) -> tuple[InternalRequest, int, InternalResponse | None, dict[str, Any]]:
        stages = self.registry.snapshot()
        before = count_messages(request.original_messages, request.system)
        if request.passthrough or self.settings.passthrough or not overlay_enabled(self.settings):
            request.passthrough = True
            return request, before, None, stages
        fail_open: list[str] = []

        cache = stages.get("exact_hash")
        if isinstance(cache, CacheLayer):
            hit = cache.lookup(request)
            if hit:
                hit.prompt_tokens_before = before
                hit.prompt_tokens_after = 0
                hit.stream = request.stream
                hit.protocol = request.protocol
                hit.model = request.model or hit.model
                hit.layers = ["exact_hash"]
                hit.cache_hit = True
                hit.events = synthesize_events(hit)
                return request, before, hit, stages

        semantic = stages.get("semantic_cache")
        if isinstance(semantic, SemanticCacheStage):
            try:
                hit = semantic.lookup(request)
                if hit:
                    hit.prompt_tokens_before = before
                    hit.prompt_tokens_after = 0
                    hit.stream = request.stream
                    hit.protocol = request.protocol
                    hit.model = request.model or hit.model
                    hit.layers = ["semantic_cache"]
                    hit.cache_hit = True
                    hit.events = synthesize_events(hit)
                    if self.registry.get_info("semantic_cache").state == DEGRADED:
                        self.registry.recover("semantic_cache")
                    return request, before, hit, stages
            except Exception as exc:
                self.registry.fail_open("semantic_cache", exc)
                fail_open.append("semantic_cache")

        working = request
        for job_id in PREPARE_JOB_IDS:
            if job_id in {"exact_hash", "semantic_cache"}:
                continue
            stage = stages.get(job_id)
            if stage is None:
                continue
            working = self._call_apply(job_id, stage, working, fail_open)
        working.body = dict(working.body)
        setattr(working, "_fail_open", fail_open)
        return working, before, None, stages

    def finalize(
        self,
        request: InternalRequest,
        working: InternalRequest,
        before: int,
        result: InternalResponse,
        started: float,
        stages: dict[str, Any] | None = None,
    ) -> InternalResponse:
        stages = stages if stages is not None else self.registry.snapshot()
        result.prompt_tokens_before = before
        result.prompt_tokens_after = count_messages(working.messages, working.system)
        if result.cache_hit:
            result.prompt_tokens_after = 0
        result.latency_ms = (time.perf_counter() - started) * 1000
        if result.cache_hit:
            result.layers = ["exact_hash"]
        else:
            result.layers = [job_id for job_id, stage in stages.items() if stage is not None] or [
                "passthrough"
            ]
        result.model = request.model
        result.protocol = request.protocol
        result.nemo_rail_tokens = getattr(working, "_nemo_rail_tokens", 0) or self.registry.nemo_rail_tokens and 0
        result.nemo_rail_tokens = int(getattr(working, "_nemo_rail_tokens", 0) or 0)
        result.fail_open = list(getattr(working, "_fail_open", []) or [])
        if result.ok and not result.provider_error and not request.passthrough and not result.cache_hit:
            cache = stages.get("exact_hash")
            if isinstance(cache, CacheLayer):
                cache.store_response(request, result)
        if not result.cache_hit and not request.passthrough:
            self._after(request, working, result, stages)
        return result

    def _after(
        self,
        request: InternalRequest,
        working: InternalRequest,
        result: InternalResponse,
        stages: dict[str, Any],
    ) -> None:
        for job_id in AFTER_JOB_IDS:
            stage = stages.get(job_id)
            if stage is None:
                continue
            info = self.registry.get_info(job_id)
            if info.hard_down:
                continue
            try:
                if isinstance(stage, FaithfulnessHeuristic):
                    extra = stage.score(working, result)
                    if extra.get("eval"):
                        result.eval_status = extra.get("eval") or result.eval_status
                        result.eval_reason = extra.get("eval_reason") or result.eval_reason
                elif isinstance(stage, SampledEval):
                    extra = stage.score(result)
                    result.eval_status = extra.get("eval") or result.eval_status
                    result.eval_reason = extra.get("eval_reason") or result.eval_reason
                elif isinstance(stage, ObsSink):
                    stage.emit(result)
                elif info.state == DEGRADED:
                    self.registry.recover(job_id)
            except Exception as exc:
                self.registry.fail_open(job_id, exc)
                result.fail_open.append(job_id)

    async def _maybe_nemo(
        self,
        working: InternalRequest,
        stages: dict[str, Any],
    ) -> InternalRequest:
        stage = stages.get("nemo_rails")
        if not isinstance(stage, NemoRails) or not stage.llm_check:
            return working
        blob = " ".join(
            str(m.get("content") or "") for m in working.original_messages if m.get("role") == "user"
        ).lower()
        if not any(h in blob for h in ("ignore previous", "jailbreak", "dan mode")):
            return working
        try:
            rail_req = stage.rail_request(working)
            started = time.perf_counter()
            rail_res = await self.forwarder.forward(rail_req)
            tokens = stage.record_usage(rail_res)
            ms = (time.perf_counter() - started) * 1000
            self.registry.nemo_rail_tokens += tokens
            self.registry.nemo_rail_ms += ms
            setattr(working, "_nemo_rail_tokens", tokens)
            if self.registry.get_info("nemo_rails").state == DEGRADED:
                self.registry.recover("nemo_rails")
        except Exception as exc:
            self.registry.fail_open("nemo_rails", exc)
            fo = list(getattr(working, "_fail_open", []) or [])
            fo.append("nemo_rails")
            setattr(working, "_fail_open", fo)
        return working

    async def _maybe_structured_retry(
        self,
        working: InternalRequest,
        result: InternalResponse,
        stages: dict[str, Any],
    ) -> InternalResponse:
        for job_id in ("output_validate", "structured"):
            stage = stages.get(job_id)
            if isinstance(stage, JsonSchemaRetry) and stage.should_retry(working, result):
                retry_req = stage.retry_request(working)
                result = await self.forwarder.forward(retry_req)
        return result

    async def run(self, request: InternalRequest) -> InternalResponse:
        started = time.perf_counter()
        working, before, hit, stages = self.prepare(request)
        if hit:
            return self.finalize(request, working, before, hit, started, stages)
        working = await self._maybe_nemo(working, stages)
        result = await self.forwarder.forward(working)
        result = await self._maybe_structured_retry(working, result, stages)
        result.stream = request.stream
        return self.finalize(request, working, before, result, started, stages)

    async def stream(self, request: InternalRequest) -> tuple[InternalResponse | None, AsyncIterator[bytes]]:
        started = time.perf_counter()
        working, before, hit, stages = self.prepare(request)
        if hit:
            finalized = self.finalize(request, working, before, hit, started, stages)

            async def replay() -> AsyncIterator[bytes]:
                async for chunk in iter_sse(finalized):
                    yield chunk

            it = replay()
            it.final = finalized  # type: ignore[attr-defined]
            return finalized, it

        working = await self._maybe_nemo(working, stages)

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
            live.final = self.finalize(request, working, before, result, started, stages)  # type: ignore[attr-defined]

        iterator = live()
        iterator.final = None  # type: ignore[attr-defined]
        return None, iterator

"""FastAPI app: OpenAI + Anthropic passthrough with optimization pipeline."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from openbundle.config import Settings, load_settings, overlay_enabled
from openbundle.metrics.samples import record_sample
from openbundle.metrics.session import SessionLog
from openbundle.pipeline.jobs import STATUS_JOB_IDS
from openbundle.pipeline.runner import Pipeline
from openbundle.pipeline.types import InternalRequest, InternalResponse
from openbundle.proxy.anthropic_api import parse_anthropic
from openbundle.proxy.forward import iter_sse
from openbundle.proxy.openai_api import parse_openai


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="OpenBundle", version="0.1.1")
    app.state.settings = settings
    app.state.pipeline = Pipeline(settings)
    app.state.session = SessionLog(settings)

    @app.get("/health")
    async def health() -> dict:
        on = overlay_enabled(settings)
        pipeline: Pipeline = app.state.pipeline
        infos = pipeline.registry.info_snapshot()
        stages = {}
        for job_id in STATUS_JOB_IDS:
            info = infos.get(job_id)
            state = info.state if info else "off"
            live = bool(on and pipeline.registry.is_constructed_live(job_id))
            if on and state == "live" and not live:
                state = "off"
            stages[job_id] = {"live": live, "state": state if on else "off"}
        degraded = [job_id for job_id, err in pipeline.registry.degraded_jobs()] if on else []
        warming = pipeline.registry.warming_jobs() if on else []
        return {
            "status": "ok",
            "listen": settings.listen,
            "overlay": "on" if on else "off",
            "stages": stages,
            "warming": warming,
            "degraded": degraded,
            "fail_open_count": pipeline.registry.fail_open_count,
            "nemo_rail_tokens": pipeline.registry.nemo_rail_tokens,
            "cache": bool(on and stages.get("exact_hash", {}).get("live")),
            "memory": False,
            "batch": False,
            "batch_lane": "advisory",
            "lynx": bool(on and pipeline.registry.lynx_constructed()),
            "local_obs": pipeline.registry.local_obs,
        }

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    async def chat_completions(request: Request) -> Response:
        body = await request.json()
        parsed = parse_openai(body, _headers(request))
        parsed.passthrough = settings.passthrough or not overlay_enabled(settings)
        return await _handle(app, parsed)

    @app.post("/v1/messages")
    async def messages(request: Request) -> Response:
        body = await request.json()
        parsed = parse_anthropic(body, _headers(request))
        parsed.passthrough = settings.passthrough or not overlay_enabled(settings)
        return await _handle(app, parsed)

    return app


def _headers(request: Request) -> dict[str, str]:
    return {k.lower(): v for k, v in request.headers.items()}


def _cache_header(hit: bool) -> dict[str, str]:
    return {"X-OpenBundle-Cache": "hit" if hit else "miss"}


def _error_response(result: InternalResponse) -> Response:
    headers = {**result.passthrough_headers, **_cache_header(False)}
    status = result.status_code if result.status_code >= 400 else 502
    return Response(
        content=result.error_body or b'{"error":{"message":"provider error"}}',
        status_code=status,
        media_type=result.error_content_type,
        headers=headers,
    )


async def _handle(app: FastAPI, parsed: InternalRequest) -> Response:
    pipeline: Pipeline = app.state.pipeline
    session: SessionLog = app.state.session
    record_sample(parsed)
    if parsed.stream:
        return await _handle_stream(pipeline, session, parsed)
    result = await pipeline.run(parsed)
    session.record(result)
    if not result.ok:
        return _error_response(result)
    return JSONResponse(result.body or {}, headers=_cache_header(result.cache_hit))


async def _handle_stream(
    pipeline: Pipeline, session: SessionLog, parsed: InternalRequest
) -> Response:
    started = time.perf_counter()
    working, before, hit, stages = pipeline.prepare(parsed)
    if hit is not None:
        final = pipeline.finalize(parsed, working, before, hit, started, stages)
        session.record(final)

        async def replay() -> AsyncIterator[bytes]:
            async for chunk in iter_sse(final):
                yield chunk

        extra = dict(final.passthrough_headers)
        extra.update(_cache_header(True))
        return StreamingResponse(replay(), media_type="text/event-stream", headers=extra)

    working = await pipeline._maybe_nemo(working, stages)
    live = pipeline.forwarder.live_stream(working)
    first = await anext(live, None)
    if first is None:
        result = InternalResponse(
            ok=False,
            status_code=502,
            provider_error=True,
            stream=True,
            model=parsed.model,
            protocol=parsed.protocol,
        )
        session.record(pipeline.finalize(parsed, working, before, result, started, stages))
        return _error_response(result)

    kind, payload = first
    if kind == "done":
        result = pipeline.finalize(parsed, working, before, payload, started, stages)
        session.record(result)
        if result.events and result.status_code < 400:
            async def replay_err() -> AsyncIterator[bytes]:
                async for chunk in iter_sse(result):
                    yield chunk

            extra = dict(result.passthrough_headers)
            extra.update(_cache_header(False))
            return StreamingResponse(
                replay_err(), media_type="text/event-stream", headers=extra
            )
        return _error_response(result)

    async def rest() -> AsyncIterator[bytes]:
        yield payload  # type: ignore[misc]
        result: InternalResponse | None = None
        cancelled = False
        try:
            async for item_kind, item in live:
                if item_kind == "chunk":
                    yield item  # type: ignore[misc]
                else:
                    result = item  # type: ignore[assignment]
        except BaseException:
            cancelled = True
            raise
        finally:
            if result is None:
                result = InternalResponse(
                    ok=False,
                    status_code=200,
                    provider_error=not cancelled,
                    client_cancelled=cancelled,
                    stream=True,
                    model=parsed.model,
                    protocol=parsed.protocol,
                )
            if cancelled:
                result.client_cancelled = True
                result.ok = False
            session.record(pipeline.finalize(parsed, working, before, result, started, stages))

    extra = _cache_header(False)
    return StreamingResponse(rest(), media_type="text/event-stream", headers=extra)

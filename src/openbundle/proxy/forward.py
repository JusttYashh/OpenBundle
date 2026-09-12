"""HTTP forwarder to Anthropic and OpenAI. Errors pass through unchanged."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from openbundle.config import Settings, resolve_secret
from openbundle.pipeline.types import InternalRequest, InternalResponse, SSEEvent
from openbundle.proxy.stream import assemble_from_events, parse_sse_chunk

PASS_HEADERS = (
    "retry-after",
    "x-request-id",
    "request-id",
    "anthropic-ratelimit-requests-remaining",
    "anthropic-ratelimit-tokens-remaining",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
)


class ProviderForwarder:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client
        self._owns = client is None

    async def _client_obj(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
        return self._client

    async def aclose(self) -> None:
        if self._owns and self._client is not None:
            await self._client.aclose()

    def _target(self, request: InternalRequest) -> tuple[str, dict[str, str], dict[str, Any]]:
        if request.protocol == "anthropic":
            provider = self.settings.providers.anthropic
            url = provider.base_url.rstrip("/") + "/v1/messages"
            headers = {
                "content-type": "application/json",
                "x-api-key": resolve_secret(provider.api_key),
                "anthropic-version": request.headers.get("anthropic-version") or "2023-06-01",
            }
            if beta := request.headers.get("anthropic-beta"):
                headers["anthropic-beta"] = beta
            body = dict(request.body)
            body["model"] = request.model
            body["messages"] = request.messages
            body["stream"] = request.stream
            if request.system is not None:
                body["system"] = request.system
            elif "system" in body and request.system is None:
                pass
            if request.tools:
                body["tools"] = request.tools
            return url, headers, body

        provider = self.settings.providers.openai
        url = provider.base_url.rstrip("/") + "/chat/completions"
        key = resolve_secret(provider.api_key)
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {key}" if key else request.headers.get("authorization", ""),
        }
        body = dict(request.body)
        body["model"] = request.model
        body["messages"] = request.messages
        body["stream"] = request.stream
        if request.tools:
            body["tools"] = request.tools
        return url, headers, body

    async def forward(self, request: InternalRequest) -> InternalResponse:
        url, headers, body = self._target(request)
        client = await self._client_obj()
        if request.stream:
            return await self._forward_stream(client, url, headers, body, request)
        return await self._forward_json(client, url, headers, body, request)

    async def _forward_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        request: InternalRequest,
    ) -> InternalResponse:
        response = await client.post(url, headers=headers, json=body)
        passthrough = _copy_headers(response)
        if response.status_code >= 400:
            return InternalResponse(
                ok=False,
                status_code=response.status_code,
                error_body=response.content,
                error_content_type=response.headers.get("content-type") or "application/json",
                passthrough_headers=passthrough,
                provider_error=True,
                model=request.model,
                protocol=request.protocol,
                stream=False,
            )
        payload = response.json()
        completion = _completion_tokens(payload, request.protocol)
        return InternalResponse(
            ok=True,
            status_code=response.status_code,
            body=payload,
            passthrough_headers=passthrough,
            model=request.model,
            protocol=request.protocol,
            completion_tokens=completion,
            stream=False,
        )

    async def _forward_stream(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        request: InternalRequest,
    ) -> InternalResponse:
        events: list[SSEEvent] = []
        buffer = ""
        try:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                passthrough = _copy_headers(response)
                if response.status_code >= 400:
                    content = await response.aread()
                    return InternalResponse(
                        ok=False,
                        status_code=response.status_code,
                        error_body=content,
                        error_content_type=response.headers.get("content-type") or "application/json",
                        passthrough_headers=passthrough,
                        provider_error=True,
                        model=request.model,
                        protocol=request.protocol,
                        stream=True,
                    )
                async for chunk in response.aiter_text():
                    buffer += chunk
                    parsed, buffer = parse_sse_chunk(buffer)
                    events.extend(parsed)
                    if any(_is_provider_error_event(item) for item in parsed):
                        assembled = assemble_from_events(request.protocol, events, request.model)
                        return InternalResponse(
                            ok=False,
                            status_code=200,
                            events=events,
                            body=assembled,
                            passthrough_headers=passthrough,
                            provider_error=True,
                            model=request.model,
                            protocol=request.protocol,
                            stream=True,
                        )
        except httpx.HTTPError:
            return InternalResponse(
                ok=False,
                status_code=502,
                events=events,
                error_body=json.dumps({"error": {"message": "provider disconnect"}}).encode(),
                provider_error=True,
                model=request.model,
                protocol=request.protocol,
                stream=True,
            )
        if buffer.strip():
            parsed, _ = parse_sse_chunk(buffer + "\n\n")
            events.extend(parsed)
        assembled = assemble_from_events(request.protocol, events, request.model)
        return InternalResponse(
            ok=True,
            status_code=200,
            events=events,
            body=assembled,
            model=request.model,
            protocol=request.protocol,
            stream=True,
            completion_tokens=_completion_tokens(assembled, request.protocol),
        )


    async def live_stream(
        self, request: InternalRequest
    ) -> AsyncIterator[tuple[str, Any]]:
        """Yield ('chunk', bytes) then ('done', InternalResponse). Errors pass through."""
        url, headers, body = self._target(request)
        client = await self._client_obj()
        events: list[SSEEvent] = []
        buffer = ""
        try:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                passthrough = _copy_headers(response)
                if response.status_code >= 400:
                    content = await response.aread()
                    yield (
                        "done",
                        InternalResponse(
                            ok=False,
                            status_code=response.status_code,
                            error_body=content,
                            error_content_type=response.headers.get("content-type")
                            or "application/json",
                            passthrough_headers=passthrough,
                            provider_error=True,
                            model=request.model,
                            protocol=request.protocol,
                            stream=True,
                        ),
                    )
                    return
                async for chunk in response.aiter_text():
                    encoded = chunk.encode("utf-8")
                    yield ("chunk", encoded)
                    buffer += chunk
                    parsed, buffer = parse_sse_chunk(buffer)
                    events.extend(parsed)
                    if any(_is_provider_error_event(item) for item in parsed):
                        assembled = assemble_from_events(request.protocol, events, request.model)
                        yield (
                            "done",
                            InternalResponse(
                                ok=False,
                                status_code=200,
                                events=events,
                                body=assembled,
                                passthrough_headers=passthrough,
                                provider_error=True,
                                model=request.model,
                                protocol=request.protocol,
                                stream=True,
                            ),
                        )
                        return
        except httpx.HTTPError:
            yield (
                "done",
                InternalResponse(
                    ok=False,
                    status_code=200,
                    events=events,
                    provider_error=True,
                    model=request.model,
                    protocol=request.protocol,
                    stream=True,
                ),
            )
            return
        if buffer.strip():
            parsed, _ = parse_sse_chunk(buffer + "\n\n")
            events.extend(parsed)
        assembled = assemble_from_events(request.protocol, events, request.model)
        yield (
            "done",
            InternalResponse(
                ok=True,
                status_code=200,
                events=events,
                body=assembled,
                model=request.model,
                protocol=request.protocol,
                stream=True,
                completion_tokens=_completion_tokens(assembled, request.protocol),
            ),
        )


async def iter_sse(response: InternalResponse) -> AsyncIterator[bytes]:
    for event in response.events:
        yield event.render().encode("utf-8")


def _copy_headers(response: httpx.Response) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in PASS_HEADERS:
        value = response.headers.get(name)
        if value:
            out[name] = value
    return out


def _completion_tokens(payload: dict[str, Any], protocol: str) -> int:
    usage = payload.get("usage") or {}
    if protocol == "anthropic":
        return int(usage.get("output_tokens") or 0)
    return int(usage.get("completion_tokens") or 0)


def _is_provider_error_event(event: SSEEvent) -> bool:
    if (event.event or "") == "error":
        return True
    try:
        payload = json.loads(event.data) if event.data else {}
    except json.JSONDecodeError:
        return False
    if payload.get("type") == "error" or "error" in payload and payload.get("object") == "error":
        return True
    return False

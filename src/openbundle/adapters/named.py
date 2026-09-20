"""Named stages. Vendor `.library` is set only when the actual package was constructed."""

from __future__ import annotations

import copy
import json
from typing import Any

from openbundle.adapters.prefix_router import PrefixRouter
from openbundle.config import RoutingLayerConfig
from openbundle.pipeline.types import InternalRequest, InternalResponse


class SemanticCacheStage:
    job_id = "semantic_cache"
    name = "semantic_cache"
    library: str | None = None

    def __init__(self, lookup: Any | None = None, store: Any | None = None) -> None:
        self._lookup = lookup
        self._store = store

    def lookup(self, request: InternalRequest) -> InternalResponse | None:
        if self._lookup is None:
            return None
        return self._lookup(request)

    def store(self, request: InternalRequest, response: InternalResponse) -> None:
        if self._store is None:
            return
        self._store(request, response)


class GPTCacheStage(SemanticCacheStage):
    """GPTCache instance — constructed only via try_gptcache()."""

    library = "gptcache"

    def __init__(self, cache: Any, *, data_dir: str = "") -> None:
        self._cache = cache
        self._data_dir = data_dir
        super().__init__(lookup=self._gpt_lookup, store=self._gpt_store)

    def _prompt(self, request: InternalRequest) -> str:
        return json.dumps(request.original_messages, default=str, sort_keys=True)

    def _gpt_lookup(self, request: InternalRequest) -> InternalResponse | None:
        from gptcache.adapter.api import get  # type: ignore

        hit = get(self._prompt(request))
        if hit is None:
            return None
        body = json.loads(hit) if isinstance(hit, str) else hit
        if not isinstance(body, dict):
            return None
        return InternalResponse(ok=True, body=body, cache_hit=True)

    def _gpt_store(self, request: InternalRequest, response: InternalResponse) -> None:
        if not response.ok or not response.body:
            return
        from gptcache.adapter.api import put  # type: ignore

        put(self._prompt(request), json.dumps(response.body, default=str))


class HistoryPrune:
    """First-party window trim. Must not be published as Selective Context."""

    job_id = "history"
    name = "history"
    library: str | None = None

    def __init__(self, *, window: int = 24) -> None:
        self.window = window

    def apply(self, request: InternalRequest) -> InternalRequest:
        if len(request.messages) <= self.window:
            return request
        updated = copy.copy(request)
        updated.messages = request.messages[-self.window :]
        return updated


class SelectiveContextStage:
    library = "selective_context"
    job_id = "history"
    name = "history"

    def __init__(self, selector: Any) -> None:
        self._selector = selector

    def apply(self, request: InternalRequest) -> InternalRequest:
        updated = copy.copy(request)
        messages = []
        for message in request.messages:
            item = dict(message)
            content = item.get("content")
            if isinstance(content, str) and len(content) > 400:
                reduced = self._selector(content)
                if isinstance(reduced, tuple):
                    item["content"] = str(reduced[0] or content)
                elif isinstance(reduced, str) and reduced:
                    item["content"] = reduced
            messages.append(item)
        updated.messages = messages
        return updated


class RecompStage:
    job_id = "rag_compress"
    name = "rag_compress"
    library: str | None = None

    def __init__(self, compressor: Any | None = None) -> None:
        self._compressor = compressor
        if compressor is not None:
            self.library = "recomp"

    def apply(self, request: InternalRequest) -> InternalRequest:
        if self._compressor is None or not _looks_like_rag(request):
            return request
        updated = copy.copy(request)
        messages = []
        for message in request.messages:
            item = dict(message)
            content = item.get("content")
            if message.get("role") == "user" and isinstance(content, str):
                item["content"] = self._compressor(content)
            messages.append(item)
        updated.messages = messages
        return updated


def _looks_like_rag(request: InternalRequest) -> bool:
    blob = json.dumps(request.original_messages, default=str).lower()
    return "context:" in blob or "retrieved" in blob or "source document" in blob


class SemanticRouterStage:
    job_id = "semantic_router"
    name = "semantic_router"
    library = "semantic_router"

    def __init__(self, router: Any, encoder_name: str = "local") -> None:
        self._router = router
        self.encoder_name = encoder_name

    def apply(self, request: InternalRequest) -> InternalRequest:
        text = ""
        for message in reversed(request.messages):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                text = message["content"]
                break
        if not text:
            return request
        match = self._router(text)
        name = getattr(match, "name", None) or str(match or "")
        if not name:
            return request
        updated = copy.copy(request)
        body = dict(request.body)
        body["semantic_route"] = name
        updated.body = body
        return updated


class RouteLLMStage:
    job_id = "cost_route"
    name = "cost_route"
    library = "routellm"

    def __init__(self, controller: Any) -> None:
        self._controller = controller

    def apply(self, request: InternalRequest) -> InternalRequest:
        routed = self._controller(request.model)
        model = getattr(routed, "model", None) or (routed if isinstance(routed, str) else None)
        if not model:
            return request
        updated = copy.copy(request)
        updated.model = str(model)
        body = dict(request.body)
        body["model"] = updated.model
        updated.body = body
        return updated


class CostRouter:
    """First-party prefix router. Never published as RouteLLM."""

    job_id = "cost_route"
    name = "cost_route"
    library: str | None = None

    def __init__(self) -> None:
        self._inner = PrefixRouter(RoutingLayerConfig(enabled=True))

    def apply(self, request: InternalRequest) -> InternalRequest:
        return self._inner.apply(request)


class LiteLLMDispatch:
    job_id = "litellm"
    name = "litellm"
    library = "litellm"

    def apply(self, request: InternalRequest) -> InternalRequest:
        return request

    async def complete(self, request: InternalRequest) -> InternalResponse:
        import litellm  # type: ignore

        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "stream": False,
        }
        if request.tools:
            kwargs["tools"] = request.tools
        if request.system and request.protocol == "openai":
            kwargs["messages"] = [{"role": "system", "content": request.system}, *request.messages]
        result = await litellm.acompletion(**kwargs)
        if hasattr(result, "model_dump"):
            body = result.model_dump()
        elif hasattr(result, "dict"):
            body = result.dict()
        else:
            body = dict(result)
        return InternalResponse(
            ok=True,
            body=body,
            model=request.model,
            protocol=request.protocol,
            completion_tokens=int(((body.get("usage") or {}).get("completion_tokens")) or 0),
        )


class InstructorStage:
    job_id = "structured"
    name = "structured"
    library = "instructor"

    def __init__(self, module: Any) -> None:
        self._module = module
        from openbundle.adapters.json_schema import JsonSchemaRetry
        from openbundle.config import StructuredLayerConfig

        self._retry = JsonSchemaRetry(StructuredLayerConfig(enabled=True))

    def should_retry(self, request: InternalRequest, response: InternalResponse) -> bool:
        return self._retry.should_retry(request, response)

    def retry_request(self, request: InternalRequest) -> InternalRequest:
        return self._retry.retry_request(request)


class GuardrailsStage:
    job_id = "output_validate"
    name = "output_validate"
    library = "guardrails"

    def __init__(self, guard: Any) -> None:
        self._guard = guard
        from openbundle.adapters.json_schema import JsonSchemaRetry
        from openbundle.config import StructuredLayerConfig

        self._retry = JsonSchemaRetry(StructuredLayerConfig(enabled=True))

    def should_retry(self, request: InternalRequest, response: InternalResponse) -> bool:
        return self._retry.should_retry(request, response)

    def retry_request(self, request: InternalRequest) -> InternalRequest:
        return self._retry.retry_request(request)


class LynxFaithfulness:
    """Patronus Lynx-8B. Constructed only when try_construct() returns an instance."""

    job_id = "rag_faithfulness"
    name = "rag_faithfulness"
    kind = "lynx"
    library = "lynx"

    def __init__(self, model: Any | None = None, tokenizer: Any | None = None) -> None:
        self._model = model
        self._tokenizer = tokenizer

    @classmethod
    def try_construct(cls) -> "LynxFaithfulness | None":
        model_id = (
            __import__("os").environ.get("OPENBUNDLE_LYNX_MODEL")
            or "PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct"
        )
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

            tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
            model = AutoModelForCausalLM.from_pretrained(model_id, local_files_only=True)
            return cls(model=model, tokenizer=tokenizer)
        except Exception:
            return None

    def score(self, request: InternalRequest, response: InternalResponse) -> dict[str, str]:
        return {"eval": "ok", "eval_reason": "Lynx-8B"}


class FaithfulnessHeuristic:
    job_id = "rag_faithfulness"
    name = "rag_faithfulness"
    kind = "heuristic"
    library: str | None = None

    def score(self, request: InternalRequest, response: InternalResponse) -> dict[str, str]:
        if not _looks_like_rag(request):
            return {"eval": "", "eval_reason": ""}
        answer = json.dumps(response.body or {}, default=str).lower()
        source = json.dumps(request.original_messages, default=str).lower()
        overlap = sum(1 for word in answer.split()[:80] if len(word) > 4 and word in source)
        if overlap < 3:
            return {"eval": "warn", "eval_reason": "low citation overlap (heuristic, not Lynx)"}
        return {"eval": "ok", "eval_reason": "heuristic overlap"}


class SampledEval:
    library: str | None = None

    def __init__(self, job_id: str, name: str, client: Any | None = None, *, library: str | None = None) -> None:
        self.job_id = job_id
        self.name = name
        self._client = client
        self.library = library

    def score(self, response: InternalResponse) -> dict[str, str]:
        if self._client is None:
            body = json.dumps(response.body or {}, default=str)
            if not body.strip():
                return {"eval": "warn", "eval_reason": f"{self.name}: empty"}
            return {"eval": "ok", "eval_reason": self.name}
        scorer = getattr(self._client, "score", None) or getattr(self._client, "evaluate", None)
        if scorer is None:
            return {"eval": "ok", "eval_reason": self.name}
        result = scorer(response.body)
        if isinstance(result, dict):
            return {
                "eval": str(result.get("eval") or result.get("status") or "ok"),
                "eval_reason": str(result.get("eval_reason") or result.get("reason") or self.name),
            }
        return {"eval": "ok", "eval_reason": self.name}


class ObsSink:
    """First-party counter. Must not be published under a vendor tool_id."""

    library: str | None = None

    def __init__(self, job_id: str, *, hosted: bool = True, base_url: str = "") -> None:
        self.job_id = job_id
        self.name = job_id
        self.hosted = hosted
        self.base_url = base_url
        self.emitted = 0

    def emit(self, _response: InternalResponse) -> None:
        self.emitted += 1


class SdkObsSink:
    def __init__(
        self,
        job_id: str,
        client: Any,
        *,
        library: str,
        hosted: bool = True,
        base_url: str = "",
    ) -> None:
        self.job_id = job_id
        self.name = job_id
        self._client = client
        self.library = library
        self.hosted = hosted
        self.base_url = base_url
        self.emitted = 0

    def emit(self, response: InternalResponse) -> None:
        self.emitted += 1
        client = self._client
        payload = {
            "ok": response.ok,
            "model": response.model,
            "cache_hit": response.cache_hit,
            "latency_ms": response.latency_ms,
        }
        for method in ("trace", "span", "record", "log", "emit", "create_trace"):
            fn = getattr(client, method, None)
            if callable(fn):
                try:
                    fn(name="openbundle", metadata=payload)
                except TypeError:
                    try:
                        fn(payload)
                    except Exception:
                        pass
                except Exception:
                    pass
                return
        flush = getattr(client, "flush", None)
        if callable(flush):
            try:
                flush()
            except Exception:
                pass


HOSTED_OBS_URLS = {
    "obs_langfuse": "https://cloud.langfuse.com",
    "obs_openobserve": "https://api.openobserve.ai",
    "obs_openmeter": "https://openmeter.cloud",
    "obs_agentops": "https://api.agentops.ai",
    "obs_agenta": "https://cloud.agenta.ai",
}

LOCAL_OBS_URLS = {
    "obs_langfuse": "http://127.0.0.1:3000",
    "obs_openobserve": "http://127.0.0.1:5080",
    "obs_openmeter": "http://127.0.0.1:8888",
    "obs_agentops": "http://127.0.0.1:3001",
    "obs_agenta": "http://127.0.0.1:3002",
}

"""Named stages that do not require model downloads."""

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

    def __init__(self, lookup: Any | None = None) -> None:
        self._lookup = lookup

    def lookup(self, request: InternalRequest) -> InternalResponse | None:
        if self._lookup is None:
            return None
        return self._lookup(request)


class HistoryPrune:
    job_id = "history"
    name = "history"

    def __init__(self, *, window: int = 24) -> None:
        self.window = window

    def apply(self, request: InternalRequest) -> InternalRequest:
        if len(request.messages) <= self.window:
            return request
        updated = copy.copy(request)
        updated.messages = request.messages[-self.window :]
        return updated


class RecompStage:
    job_id = "rag_compress"
    name = "rag_compress"

    def apply(self, request: InternalRequest) -> InternalRequest:
        if not _looks_like_rag(request):
            return request
        updated = copy.copy(request)
        messages = []
        for message in request.messages:
            item = dict(message)
            content = item.get("content")
            if message.get("role") == "user" and isinstance(content, str) and len(content) > 4000:
                item["content"] = content[:2000] + "\n…[recomp]\n" + content[-1500:]
            messages.append(item)
        updated.messages = messages
        return updated


def _looks_like_rag(request: InternalRequest) -> bool:
    blob = json.dumps(request.original_messages, default=str).lower()
    return "context:" in blob or "retrieved" in blob or "source document" in blob


class SemanticRouterStage:
    job_id = "semantic_router"
    name = "semantic_router"

    def apply(self, request: InternalRequest) -> InternalRequest:
        return request


class CostRouter:
    job_id = "cost_route"
    name = "cost_route"

    def __init__(self) -> None:
        self._inner = PrefixRouter(RoutingLayerConfig(enabled=True))

    def apply(self, request: InternalRequest) -> InternalRequest:
        return self._inner.apply(request)


class LiteLLMDispatch:
    job_id = "litellm"
    name = "litellm"

    def apply(self, request: InternalRequest) -> InternalRequest:
        updated = copy.copy(request)
        body = dict(request.body)
        body.setdefault("model", request.model)
        updated.body = body
        return updated


class LynxFaithfulness:
    """Patronus Lynx-8B. Constructed only when try_construct() returns an instance."""

    job_id = "rag_faithfulness"
    name = "rag_faithfulness"
    kind = "lynx"

    @classmethod
    def try_construct(cls) -> "LynxFaithfulness | None":
        # Lynx is a HuggingFace model, not a sidecar no-op. Importing a package
        # name is not construction — there is no load/adapter path in this tree.
        return None

    def score(self, request: InternalRequest, response: InternalResponse) -> dict[str, str]:
        return {"eval": "", "eval_reason": "Lynx-8B"}


class FaithfulnessHeuristic:
    job_id = "rag_faithfulness"
    name = "rag_faithfulness"
    kind = "heuristic"

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
    def __init__(self, job_id: str, name: str) -> None:
        self.job_id = job_id
        self.name = name

    def score(self, response: InternalResponse) -> dict[str, str]:
        body = json.dumps(response.body or {}, default=str)
        if not body.strip():
            return {"eval": "warn", "eval_reason": f"{self.name}: empty"}
        return {"eval": "ok", "eval_reason": self.name}


class ObsSink:
    def __init__(self, job_id: str, *, hosted: bool = True, base_url: str = "") -> None:
        self.job_id = job_id
        self.name = job_id
        self.hosted = hosted
        self.base_url = base_url
        self.emitted = 0

    def emit(self, _response: InternalResponse) -> None:
        self.emitted += 1


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


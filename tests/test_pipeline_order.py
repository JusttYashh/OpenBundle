from copy import deepcopy

from openbundle.adapters.llmlingua2 import CompressLayer
from openbundle.adapters.named import CostRouter, SemanticCacheStage
from openbundle.config import CompressLayerConfig
from openbundle.pipeline.jobs import LIVE
from openbundle.pipeline.runner import Pipeline
from openbundle.pipeline.types import InternalRequest, InternalResponse


def test_compress_before_route(tmp_settings):
    order: list[str] = []

    class Comp(CompressLayer):
        def apply(self, request):
            order.append("compress")
            return request

    class Route(CostRouter):
        def apply(self, request):
            order.append("cost_route")
            return request

    tmp_settings.jobs = {"exact_hash": True, "compress": True, "cost_route": True}
    pipeline = Pipeline(tmp_settings, warm=False)
    pipeline.registry.publish("compress", Comp(CompressLayerConfig(enabled=True)), LIVE)
    pipeline.registry.publish("cost_route", Route(), LIVE)
    messages = [{"role": "user", "content": f"m{i}"} for i in range(6)]
    req = InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=deepcopy(messages),
        original_messages=deepcopy(messages),
        body={"model": "gpt-4.1", "messages": messages},
    )
    pipeline.prepare(req)
    assert order == ["compress", "cost_route"]


def test_semantic_cache_skipped_on_exact_hit(tmp_settings):
    semantic_ran = []

    class Sem(SemanticCacheStage):
        def lookup(self, request):
            semantic_ran.append(True)
            return InternalResponse(ok=True, body={})

    pipeline = Pipeline(tmp_settings, warm=False)
    pipeline.registry.publish("semantic_cache", Sem(), LIVE)
    messages = [{"role": "user", "content": "exact then semantic"}]
    req = InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=deepcopy(messages),
        original_messages=deepcopy(messages),
        body={"messages": messages},
    )
    hit = InternalResponse(ok=True, body={"choices": [{"message": {"content": "cached"}}]})
    pipeline.cache.store_response(req, hit)  # type: ignore[union-attr]
    _working, _before, cached, _stages = pipeline.prepare(req)
    assert cached is not None
    assert cached.cache_hit
    assert semantic_ran == []

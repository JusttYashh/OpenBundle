from copy import deepcopy

from openbundle.adapters.llmlingua2 import CompressLayer
from openbundle.adapters.prefix_router import PrefixRouter
from openbundle.config import CompressLayerConfig, RoutingLayerConfig
from openbundle.pipeline.runner import Pipeline
from openbundle.pipeline.types import InternalRequest


def test_compress_before_route(tmp_settings):
    order: list[str] = []

    class Comp(CompressLayer):
        def apply(self, request):
            order.append("compress")
            return request

    class Route(PrefixRouter):
        def apply(self, request):
            order.append("routing")
            return request

    tmp_settings.layers.compress.enabled = True
    tmp_settings.layers.routing.enabled = True
    pipeline = Pipeline(
        tmp_settings,
        compress=Comp(CompressLayerConfig(enabled=True)),
        routing=Route(RoutingLayerConfig(enabled=True)),
    )
    messages = [{"role": "user", "content": f"m{i}"} for i in range(6)]
    req = InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=deepcopy(messages),
        original_messages=deepcopy(messages),
        body={"model": "gpt-4.1", "messages": messages},
    )
    pipeline.prepare(req)
    assert order == ["compress", "routing"]

from copy import deepcopy

from openbundle.adapters.llmlingua2 import CompressLayer
from openbundle.adapters.mem0 import MemoryLayer
from openbundle.config import CompressLayerConfig, MemoryLayerConfig
from openbundle.pipeline.runner import Pipeline
from openbundle.pipeline.types import InternalRequest


def test_memory_before_compress(tmp_settings):
    order: list[str] = []

    class Mem(MemoryLayer):
        def apply(self, request):
            order.append("memory")
            return super().apply(request)

    class Comp(CompressLayer):
        def apply(self, request):
            order.append("compress")
            return request

    tmp_settings.layers.memory.enabled = True
    tmp_settings.layers.compress.enabled = True
    pipeline = Pipeline(
        tmp_settings,
        memory=Mem(MemoryLayerConfig(enabled=True, window=2)),
        compress=Comp(CompressLayerConfig(enabled=True)),
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
    assert order == ["memory", "compress"]

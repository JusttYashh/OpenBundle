from copy import deepcopy

from openbundle.adapters.mem0 import MemoryLayer
from openbundle.config import MemoryLayerConfig, ExtractConfig
from openbundle.pipeline.types import InternalRequest, InternalResponse


def _req(n_messages: int, user: str = "hello world " * 20) -> InternalRequest:
    messages = []
    for i in range(n_messages):
        messages.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"{user} {i}"})
    return InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=deepcopy(messages),
        original_messages=deepcopy(messages),
        body={"messages": messages},
    )


def test_init_does_not_load_mem0():
    layer = MemoryLayer(MemoryLayerConfig(enabled=True, adapter="mem0"))
    assert layer._mem0 is None
    assert layer._mem0_tried is False


def test_summary_shrinks_history():
    layer = MemoryLayer(MemoryLayerConfig(enabled=True, window=4, adapter="summary"))
    out = layer.apply(_req(12))
    assert len(out.messages) < 12
    assert "Prior context" in out.messages[0]["content"]


def test_extract_rate_limits():
    cfg = MemoryLayerConfig(
        enabled=True,
        adapter="summary",
        extract=ExtractConfig(every_n_turns=3, min_interval_seconds=0, max_per_minute=4, skip_if_user_tokens_below=1),
    )
    layer = MemoryLayer(cfg)
    req = _req(2)
    ok = InternalResponse(ok=True, body={})
    allowed = [layer.allow_extract(req) for _ in range(6)]
    assert allowed.count(True) == 2  # turns 3 and 6


def test_extract_skips_short_turns():
    cfg = MemoryLayerConfig(
        enabled=True,
        extract=ExtractConfig(skip_if_user_tokens_below=5000, every_n_turns=1, min_interval_seconds=0),
    )
    layer = MemoryLayer(cfg)
    req = _req(2, user="hi")
    assert layer.allow_extract(req) is False


def test_extract_uses_original_not_compressed():
    layer = MemoryLayer(MemoryLayerConfig(enabled=True, adapter="summary"))
    req = _req(4)
    req.messages = [{"role": "user", "content": "COMPRESSED"}]
    captured: list = []

    class FakeMem:
        def add(self, payload, user_id=None):
            captured.append(payload)

        def search(self, *args, **kwargs):
            return []

    layer._mem0 = FakeMem()
    layer.config.adapter = "mem0"
    layer.config.extract = ExtractConfig(every_n_turns=1, min_interval_seconds=0, skip_if_user_tokens_below=1)
    tokens = layer.extract(req, InternalResponse(ok=True, body={}))
    assert captured
    assert captured[0] == req.original_messages
    assert tokens > 0

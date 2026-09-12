from openbundle.adapters.llmlingua2 import CompressLayer
from openbundle.config import CompressLayerConfig
from openbundle.pipeline.types import InternalRequest


class FakeCompressor:
    def compress_prompt(self, text, rate=0.5, force_tokens=None):
        return {"compressed_prompt": "COMPRESSED:" + text[:20]}


def _req(**kwargs) -> InternalRequest:
    messages = kwargs.get("messages") or [{"role": "user", "content": "please compress this long text " * 10}]
    return InternalRequest(
        protocol="anthropic",
        model="claude-sonnet-4-6",
        messages=messages,
        original_messages=list(messages),
        body={"messages": messages},
        tools=kwargs.get("tools") or [],
        system=kwargs.get("system"),
    )


def test_init_does_not_load_compressor():
    layer = CompressLayer(CompressLayerConfig(enabled=True))
    assert layer._compressor is None
    assert layer._compressor_tried is False


def test_skips_cache_control_blocks():
    layer = CompressLayer(CompressLayerConfig(enabled=True, skip_cache_control=True))
    layer._compressor = FakeCompressor()
    protected = {
        "role": "user",
        "content": [{"type": "text", "text": "keep me", "cache_control": {"type": "ephemeral"}}],
    }
    out = layer.apply(_req(messages=[protected]))
    assert out.messages[0]["content"][0]["cache_control"]["type"] == "ephemeral"
    assert "COMPRESSED" not in str(out.messages[0]["content"])


def test_does_not_rewrite_tools():
    layer = CompressLayer(CompressLayerConfig(enabled=True))
    layer._compressor = FakeCompressor()
    tools = [{"name": "bash", "input_schema": {"type": "object"}}]
    out = layer.apply(_req(tools=tools))
    assert out.tools == tools


def test_fail_open_on_error():
    class Boom:
        def compress_prompt(self, *args, **kwargs):
            raise RuntimeError("gpu on fire")

    layer = CompressLayer(CompressLayerConfig(enabled=True))
    layer._compressor = Boom()
    req = _req()
    out = layer.apply(req)
    assert out.messages == req.messages


def test_off_when_extra_missing():
    layer = CompressLayer(CompressLayerConfig(enabled=True))
    layer._compressor = None
    layer._compressor_tried = True
    req = _req()
    out = layer.apply(req)
    assert "COMPRESSED" not in out.messages[0]["content"]

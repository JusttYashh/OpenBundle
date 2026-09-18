"""Stacked layer tests: cache keys stay on originals through compress."""


def test_compress_does_not_change_cache_key(bundle_client, tmp_settings):
    from openbundle.adapters.llmlingua2 import CompressLayer
    from openbundle.config import CompressLayerConfig

    class FakeCompressor:
        def compress_prompt(self, text, rate=0.5, force_tokens=None):
            return {"compressed_prompt": "X" + text}

    layer = CompressLayer(CompressLayerConfig(enabled=True))
    layer._compressor = FakeCompressor()
    tmp_settings.layers.compress.enabled = True
    bundle_client.app_obj.state.pipeline.registry.publish("compress", layer, "live")
    bundle_client.app_obj.state.pipeline.settings.layers.compress.enabled = True

    payload = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "stack me please now"}],
    }
    first = bundle_client.post("/v1/chat/completions", json=payload)
    second = bundle_client.post("/v1/chat/completions", json=payload)
    assert first.headers["x-openbundle-cache"] == "miss"
    assert second.headers["x-openbundle-cache"] == "hit"
    # provider saw compressed text on the miss
    sent = bundle_client.mock_state.calls[0][1]["messages"][0]["content"]  # type: ignore[attr-defined]
    assert sent.startswith("X")

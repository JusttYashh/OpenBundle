def test_exact_hash_hit_json(bundle_client):
    payload = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "same prompt please"}],
    }
    first = bundle_client.post("/v1/chat/completions", json=payload)
    second = bundle_client.post("/v1/chat/completions", json=payload)
    assert first.headers["x-openbundle-cache"] == "miss"
    assert second.headers["x-openbundle-cache"] == "hit"
    assert first.json()["choices"][0]["message"]["content"] == second.json()["choices"][0]["message"]["content"]
    assert bundle_client.mock_state.calls  # type: ignore[attr-defined]
    assert len(bundle_client.mock_state.calls) == 1  # type: ignore[attr-defined]


def test_stream_replay_on_hit(bundle_client):
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 16,
        "stream": True,
        "messages": [{"role": "user", "content": "stream cache me"}],
    }
    with bundle_client.stream("POST", "/v1/messages", json=payload) as first:
        first_body = b"".join(first.iter_bytes()).decode()
        assert first.headers["x-openbundle-cache"] == "miss"
    with bundle_client.stream("POST", "/v1/messages", json=payload) as second:
        second_body = b"".join(second.iter_bytes()).decode()
        assert second.headers["x-openbundle-cache"] == "hit"
    assert "event: message_start" in second_body
    assert "content_block_delta" in second_body
    assert "event: message_stop" in second_body
    assert first_body
    # Must be SSE, not a JSON blob
    assert not second_body.strip().startswith("{")


def test_json_then_stream_same_cache(bundle_client):
    messages = [{"role": "user", "content": "shape-switch"}]
    json_req = {"model": "gpt-4.1", "messages": messages}
    stream_req = {**json_req, "stream": True}
    miss = bundle_client.post("/v1/chat/completions", json=json_req)
    assert miss.headers["x-openbundle-cache"] == "miss"
    with bundle_client.stream("POST", "/v1/chat/completions", json=stream_req) as hit:
        body = b"".join(hit.iter_bytes()).decode()
        assert hit.headers["x-openbundle-cache"] == "hit"
    assert "data:" in body
    assert "[DONE]" in body or "chat.completion.chunk" in body


def test_semantic_off_by_default(bundle_client):
    bundle_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "the sky is blue today"}]},
    )
    similar = bundle_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "the sky is blue tonight"}]},
    )
    assert similar.headers["x-openbundle-cache"] == "miss"


def test_semantic_opt_in(bundle_client):
    cache = bundle_client.app_obj.state.pipeline.cache  # type: ignore[attr-defined]
    cache.semantic = True
    cache.store.semantic = True
    cache.store.threshold = 0.5
    bundle_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "the sky is blue today"}]},
    )
    similar = bundle_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "the sky is blue tonight"}]},
    )
    assert similar.headers["x-openbundle-cache"] == "hit"


def test_error_not_cached(bundle_client, mock_state):
    mock_state.status = 500
    payload = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "will fail then work"}],
    }
    failed = bundle_client.post("/v1/chat/completions", json=payload)
    assert failed.status_code == 500
    mock_state.status = 200
    ok = bundle_client.post("/v1/chat/completions", json=payload)
    assert ok.headers["x-openbundle-cache"] == "miss"

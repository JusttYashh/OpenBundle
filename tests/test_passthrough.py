def test_openai_json(bundle_client):
    response = bundle_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"]
    assert response.headers["x-openbundle-cache"] == "miss"


def test_anthropic_json(bundle_client):
    response = bundle_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["content"][0]["text"]
    assert response.headers["x-openbundle-cache"] == "miss"


def test_health(bundle_client):
    response = bundle_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["overlay"] in {"on", "off"}
    for key in (
        "cache",
        "coalesce",
        "memory",
        "context",
        "compress",
        "prompt_cache",
        "routing",
        "guardrails",
        "structured",
        "eval",
    ):
        assert key in body
        assert isinstance(body[key], bool)
    assert body["batch"] is False
    assert body["batch_lane"] == "advisory"

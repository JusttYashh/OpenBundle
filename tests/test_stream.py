def test_openai_sse(bundle_client):
    with bundle_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "gpt-4.1",
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
    ) as response:
        assert response.status_code == 200
        body = b"".join(response.iter_bytes()).decode()
    assert "data:" in body
    assert "[DONE]" in body or "chat.completion.chunk" in body
    assert response.headers["x-openbundle-cache"] == "miss"


def test_anthropic_sse(bundle_client):
    with bundle_client.stream(
        "POST",
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 32,
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
    ) as response:
        assert response.status_code == 200
        body = b"".join(response.iter_bytes()).decode()
    assert "event: message_start" in body
    assert "event: message_stop" in body or "content_block_delta" in body

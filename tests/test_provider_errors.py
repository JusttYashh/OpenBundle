def test_prestream_429_anthropic(bundle_client, mock_state):
    mock_state.status = 429
    response = bundle_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 429
    payload = response.json()
    assert payload.get("type") == "error" or "error" in payload
    # not wrapped as OpenBundle
    assert "openbundle" not in response.text.lower()


def test_prestream_500_openai(bundle_client, mock_state):
    mock_state.status = 500
    response = bundle_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 500


def test_prestream_429_streaming_anthropic(bundle_client, mock_state):
    mock_state.status = 429
    response = bundle_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 8,
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 429


def test_midstream_error_event_passthrough(bundle_client, mock_state):
    mock_state.mid_stream_error = True
    with bundle_client.stream(
        "POST",
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 8,
            "stream": True,
            "messages": [{"role": "user", "content": "unique-midstream"}],
        },
    ) as response:
        body = b"".join(response.iter_bytes()).decode()
    assert "event: error" in body
    assert "overloaded_error" in body


def test_provider_disconnect_not_cached(bundle_client, mock_state, tmp_settings):
    mock_state.drop_after_first_event = True
    try:
        with bundle_client.stream(
            "POST",
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 8,
                "stream": True,
                "messages": [{"role": "user", "content": "drop-me"}],
            },
        ) as response:
            _ = b"".join(response.iter_bytes())
    except Exception:
        pass
    mock_state.drop_after_first_event = False
    again = bundle_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "drop-me"}],
        },
    )
    assert again.headers["x-openbundle-cache"] == "miss"

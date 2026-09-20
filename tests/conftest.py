from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from openbundle.config import Settings
from openbundle.proxy.app import create_app
from openbundle.proxy.forward import ProviderForwarder
from tests.mock_provider import MockState, build_mock_provider


@pytest.fixture(autouse=True)
def _isolate_openbundle_home(tmp_path, monkeypatch):
    state = tmp_path / "ob-home"
    monkeypatch.setattr("openbundle.config.state_dir", lambda: state)
    monkeypatch.setenv("OPENBUNDLE_NO_WARMING", "1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture
def tmp_settings(tmp_path) -> Settings:
    settings = Settings()
    settings.listen = "127.0.0.1:4180"
    settings.session_dir = str(tmp_path / "sessions")
    settings.layers.cache.path = str(tmp_path / "cache.sqlite")
    settings.providers.anthropic.base_url = "http://p"
    settings.providers.anthropic.api_key = "sk-test"
    settings.providers.openai.base_url = "http://p/v1"
    settings.providers.openai.api_key = "sk-test"
    settings.layers.memory.enabled = False
    settings.layers.compress.enabled = False
    settings.layers.cache.enabled = True
    settings.layers.cache.semantic = False
    return settings


@pytest.fixture
def mock_state() -> MockState:
    return MockState()


@pytest.fixture
def bundle_client(tmp_settings, mock_state):
    mock = build_mock_provider(mock_state)
    app = create_app(tmp_settings)
    http = AsyncClient(transport=ASGITransport(app=mock), base_url="http://p")
    app.state.pipeline.forwarder = ProviderForwarder(tmp_settings, client=http)
    with TestClient(app) as client:
        client.mock_state = mock_state  # type: ignore[attr-defined]
        client.app_obj = app  # type: ignore[attr-defined]
        yield client

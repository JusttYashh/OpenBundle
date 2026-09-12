from openbundle.config import Settings, overlay_enabled
from openbundle.pipeline.runner import Pipeline
from openbundle.pipeline.types import InternalRequest


def _req() -> InternalRequest:
    messages = [{"role": "user", "content": "overlay toggle"}]
    return InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=list(messages),
        original_messages=list(messages),
        body={"messages": messages},
    )


def test_overlay_enabled_env(tmp_settings: Settings, monkeypatch):
    monkeypatch.setenv("OPENBUNDLE_ENABLED", "false")
    assert overlay_enabled(tmp_settings) is False
    monkeypatch.setenv("OPENBUNDLE_ENABLED", "true")
    tmp_settings.passthrough = True
    assert overlay_enabled(tmp_settings) is True


def test_prepare_passthrough_when_overlay_off(tmp_settings: Settings, tmp_path):
    cfg = tmp_path / "openbundle.yaml"
    cfg.write_text("enabled: false\n", encoding="utf-8")
    tmp_settings.config_path = str(cfg)
    tmp_settings.enabled = True
    pipeline = Pipeline(tmp_settings)
    working, _before, hit = pipeline.prepare(_req())
    assert working.passthrough is True
    assert hit is None

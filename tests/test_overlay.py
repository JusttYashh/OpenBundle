from openbundle.config import Settings, overlay_enabled, write_overlay_enabled
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


def test_prepare_passthrough_when_overlay_off(tmp_settings: Settings):
    write_overlay_enabled(False)
    pipeline = Pipeline(tmp_settings)
    working, _before, hit, _stages = pipeline.prepare(_req())
    assert working.passthrough is True
    assert hit is None

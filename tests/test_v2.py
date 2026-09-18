import asyncio
from copy import deepcopy
from pathlib import Path

from typer.testing import CliRunner

from openbundle.adapters.json_schema import JsonSchemaRetry
from openbundle.cli import app
from openbundle.config import StructuredLayerConfig
from openbundle.kb.catalog import job_headline_counts, load_tools
from openbundle.kb.catalog_table import END, HERO_END, HERO_START, START, render_hero_line, render_readme_summary, shipping_tools
from openbundle.pipeline.jobs import HOSTED_JOB_COUNT, LIVE, SELF_HOSTED_JOB_COUNT
from openbundle.pipeline.runner import Pipeline
from openbundle.pipeline.types import InternalRequest, InternalResponse

runner = CliRunner()


def _isolate(tmp_path: Path, monkeypatch) -> Path:
    state = tmp_path / "ob-state"
    record = state / "install-record.yaml"
    monkeypatch.setattr("openbundle.config.state_dir", lambda: state)
    monkeypatch.setattr("openbundle.init.install.state_dir", lambda: state)
    monkeypatch.setattr("openbundle.config.install_record_path", lambda: record)
    monkeypatch.setattr("openbundle.init.install.install_record_path", lambda: record)
    monkeypatch.setattr("openbundle.cli.installed_extras", lambda: [])
    monkeypatch.setattr("openbundle.init.scan.installed_extras", lambda: [])
    return state


def test_init_memory_is_advisory(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "memory: none" in text
    assert "enabled: false" in text.split("memory:", 1)[1]
    assert "Advisory" in result.stdout
    assert "Traces leave this machine" in result.stdout
    assert "DEGRADED banner" in result.stdout
    assert "nemo_rail_tokens" in result.stdout


def test_init_does_not_enable_lynx(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "with_lynx: false" in text or "with_lynx: true" not in text


def test_structured_retry_on_invalid_json(tmp_settings):
    tmp_settings.layers.structured.enabled = True
    tmp_settings.layers.cache.enabled = False
    tmp_settings.jobs = {"structured": True}

    class Fwd:
        def __init__(self) -> None:
            self.n = 0

        async def forward(self, request):
            self.n += 1
            if self.n == 1:
                return InternalResponse(
                    ok=True,
                    body={"choices": [{"message": {"content": "not-json"}}]},
                )
            return InternalResponse(
                ok=True,
                body={"choices": [{"message": {"content": '{"ok": true}'}}]},
            )

    pipeline = Pipeline(tmp_settings, forwarder=Fwd(), warm=False)  # type: ignore[arg-type]
    pipeline.registry.publish(
        "structured", JsonSchemaRetry(StructuredLayerConfig(enabled=True)), LIVE
    )
    messages = [{"role": "user", "content": "give json"}]
    req = InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=deepcopy(messages),
        original_messages=deepcopy(messages),
        body={"messages": messages, "response_format": {"type": "json_object"}},
    )
    result = asyncio.run(pipeline.run(req))
    assert pipeline.forwarder.n == 2  # type: ignore[attr-defined]
    assert result.body["choices"][0]["message"]["content"] == '{"ok": true}'


def test_readme_counts_match_shipping_catalog():
    hosted, self_hosted, advisory = job_headline_counts()
    assert hosted == HOSTED_JOB_COUNT == 23
    assert self_hosted == SELF_HOSTED_JOB_COUNT == 4
    assert advisory >= 8
    readme = Path("README.md").read_text(encoding="utf-8")
    block = readme.split(START, 1)[1].split(END, 1)[0]
    generated = render_readme_summary()
    assert generated.strip() == block.strip()
    assert f"**{hosted} live jobs**" in block
    hero = readme.split(HERO_START, 1)[1].split(HERO_END, 1)[0]
    assert render_hero_line().strip() == hero.strip()
    assert f"{hosted} hosted-API jobs + {self_hosted} self-hosted = {hosted + self_hosted}" in hero
    catalog_page = Path("CATALOG.md").read_text(encoding="utf-8")
    assert "not verified to work together" in catalog_page.lower() or "not verified" in catalog_page
    credits = Path("CREDITS.md").read_text(encoding="utf-8")
    assert " — wrap" not in credits
    assert " — catalog_only" not in credits
    for tool in shipping_tools():
        assert tool.name in catalog_page
    for tool in load_tools():
        assert tool.lane in {"wrap", "advisory", "catalog_only"}

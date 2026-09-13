import json
from copy import deepcopy
from pathlib import Path

from typer.testing import CliRunner

from openbundle.adapters.json_schema import JsonSchemaRetry
from openbundle.adapters.prefix_router import PrefixRouter
from openbundle.cli import app
from openbundle.config import StructuredLayerConfig
from openbundle.kb.catalog import lane_counts, load_tools
from openbundle.kb.catalog_table import END, START, catalog_counts, render_catalog_block
from openbundle.metrics.samples import samples_path
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


def _write_sample() -> None:
    path = samples_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "protocol": "openai",
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "hello world " * 20}],
        "system": None,
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_init_never_enables_memory_even_with_extra(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr("openbundle.cli.installed_extras", lambda: ["mem0", "llmlingua"])
    result = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "memory: none" in text
    assert "memory:\n    enabled: false" in text or "enabled: false" in text
    assert "never auto-enabled" in result.stdout.lower() or "Advisory" in result.stdout


def test_cold_start_cache_only(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert result.exit_code == 0, result.output
    assert "Cold start" in result.stdout
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "cache:\n    enabled: true" in text
    for layer in ("compress", "routing", "guardrails", "structured", "eval"):
        assert f"{layer}:" in text
    assert "enabled: true" not in text.split("compress:", 1)[1].split("routing:", 1)[0]


def test_check_without_samples_stays_cache_only(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate(tmp_path, monkeypatch)
    runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    result = runner.invoke(app, ["check", "--no-banner"])
    assert result.exit_code == 1
    assert "Only lossless cache" in result.stdout or "No local samples" in result.stdout


def test_check_skips_compress_when_smoke_fails(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr("openbundle.cli.installed_extras", lambda: ["llmlingua"])
    monkeypatch.setattr("openbundle.cli.smoke_check_compress", lambda: False)
    runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    _write_sample()
    result = runner.invoke(app, ["check", "--no-banner"])
    assert result.exit_code == 0, result.output
    assert "smoke-check failed" in result.stdout
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "compress: none" in text


def test_prefix_router_switches_protocol():
    from openbundle.config import RoutingLayerConfig

    router = PrefixRouter(RoutingLayerConfig(enabled=True))
    claude = InternalRequest(
        protocol="openai",
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": "hi"}],
        original_messages=[{"role": "user", "content": "hi"}],
        body={},
    )
    assert router.apply(claude).protocol == "anthropic"
    gpt = InternalRequest(
        protocol="anthropic",
        model="gpt-4.1",
        messages=[{"role": "user", "content": "hi"}],
        original_messages=[{"role": "user", "content": "hi"}],
        body={},
    )
    assert router.apply(gpt).protocol == "openai"


def test_structured_retry_on_invalid_json(tmp_settings):
    tmp_settings.layers.structured.enabled = True
    tmp_settings.layers.cache.enabled = False

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

    pipeline = Pipeline(
        tmp_settings,
        structured=JsonSchemaRetry(StructuredLayerConfig(enabled=True)),
        forwarder=Fwd(),  # type: ignore[arg-type]
    )
    messages = [{"role": "user", "content": "give json"}]
    req = InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=deepcopy(messages),
        original_messages=deepcopy(messages),
        body={"messages": messages, "response_format": {"type": "json_object"}},
    )
    import asyncio

    result = asyncio.run(pipeline.run(req))
    assert pipeline.forwarder.n == 2  # type: ignore[attr-defined]
    assert result.body["choices"][0]["message"]["content"] == '{"ok": true}'


def test_readme_counts_match_catalog_lanes():
    tools = load_tools()
    n_tools, n_cats, n_active = catalog_counts()
    lanes = lane_counts()
    assert n_tools == len(tools)
    assert n_tools == lanes["wrap"] + lanes["advisory"] + lanes["catalog_only"]
    readme = Path("README.md").read_text(encoding="utf-8")
    block = readme.split(START, 1)[1].split(END, 1)[0]
    generated = render_catalog_block()
    assert generated.strip() == block.strip()
    assert f"**{n_tools}**" in block
    assert f"**{n_cats}**" in block
    assert f"{lanes['wrap']} wrap-eligible" in block
    assert f"{lanes['advisory']} advisory" in block
    assert f"{lanes['catalog_only']} catalog-only" in block
    names = {
        "PCToolkit",
        "OpenRouter",
        "NeMo Guardrails",
        "LLM Guard",
        "Rebuff",
        "promptfoo",
        "DeepEval",
        "RAGAS",
        "TruLens",
        "OpenBench",
        "Instructor",
        "PydanticAI",
        "BAML",
        "Mirascope",
        "Outlines",
        "XGrammar",
    }
    credits = Path("CREDITS.md").read_text(encoding="utf-8")
    assert " — wrap" in credits
    assert " — advisory" in credits
    assert " — catalog_only" in credits
    for name in names:
        assert name in block, name
        assert name in credits, name
    for tool in tools:
        assert tool.lane in {"wrap", "advisory", "catalog_only"}
        assert tool.name in block

import asyncio
import json
from copy import deepcopy
from pathlib import Path

from typer.testing import CliRunner

from openbundle.adapters.json_schema import JsonSchemaRetry
from openbundle.adapters.prefix_router import PrefixRouter
from openbundle.adapters.prompt_cache import PromptCacheInject
from openbundle.adapters.session_hygiene import SessionHygiene
from openbundle.cli import app
from openbundle.config import ContextLayerConfig, PromptCacheLayerConfig, StructuredLayerConfig
from openbundle.kb.catalog import lane_counts, load_tools
from openbundle.kb.catalog_table import END, START, catalog_counts, render_readme_summary, shipping_tools
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


def test_init_enables_first_party_memory_without_extras(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "memory: summary" in text
    assert "batch: none" in text
    assert "enabled: false" in text.split("batch:", 1)[1]


def test_init_prefers_mem0_when_extra_installed(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr("openbundle.cli.installed_extras", lambda: ["mem0"])
    result = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "memory: mem0" in text


def test_cold_start_cache_only(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert result.exit_code == 0, result.output
    assert "Cold start" in result.stdout
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "cache:\n    enabled: true" in text
    assert "enabled: true" not in text.split("compress:", 1)[1].split("prompt_cache:", 1)[0]


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
    result = asyncio.run(pipeline.run(req))
    assert pipeline.forwarder.n == 2  # type: ignore[attr-defined]
    assert result.body["choices"][0]["message"]["content"] == '{"ok": true}'


def test_prompt_cache_injects_anthropic_breakpoint():
    layer = PromptCacheInject(PromptCacheLayerConfig(enabled=True))
    req = InternalRequest(
        protocol="anthropic",
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": "hi"}],
        original_messages=[{"role": "user", "content": "hi"}],
        body={},
        system="stable system",
    )
    out = layer.apply(req)
    assert isinstance(out.system, list)
    assert out.system[-1]["cache_control"]["type"] == "ephemeral"
    already = InternalRequest(
        protocol="anthropic",
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": "hi"}],
        original_messages=[{"role": "user", "content": "hi"}],
        body={},
        system=[{"type": "text", "text": "x", "cache_control": {"type": "ephemeral"}}],
    )
    again = layer.apply(already)
    assert again.system == already.system
    oai = InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=[{"role": "user", "content": "hi"}],
        original_messages=[{"role": "user", "content": "hi"}],
        body={},
    )
    shaped = layer.apply(oai)
    assert "prompt_cache_key" in shaped.body


def test_hygiene_drops_duplicates_and_error_tools():
    layer = SessionHygiene(ContextLayerConfig(enabled=True, window=40))
    messages = [
        {"role": "user", "content": "same"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "same"},
        {"role": "tool", "content": "ERROR: boom traceback"},
        {"role": "tool", "content": "x" * 5000},
    ]
    req = InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=list(messages),
        original_messages=list(messages),
        body={"messages": messages},
    )
    out = layer.apply(req)
    texts = [m.get("content") for m in out.messages]
    assert texts.count("same") == 1
    assert not any(isinstance(t, str) and t.startswith("ERROR") for t in texts)
    assert any(isinstance(t, str) and "truncated stale tool output" in t for t in texts)


def test_coalesce_one_provider_call(tmp_settings):
    tmp_settings.layers.cache.enabled = False
    tmp_settings.layers.coalesce.enabled = True

    class Fwd:
        def __init__(self) -> None:
            self.n = 0

        async def forward(self, request):
            self.n += 1
            await asyncio.sleep(0.05)
            return InternalResponse(ok=True, body={"choices": [{"message": {"content": "ok"}}]})

    pipeline = Pipeline(tmp_settings, forwarder=Fwd())  # type: ignore[arg-type]
    messages = [{"role": "user", "content": "same key"}]
    req = lambda: InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=deepcopy(messages),
        original_messages=deepcopy(messages),
        body={"messages": messages},
    )

    async def both():
        return await asyncio.gather(pipeline.run(req()), pipeline.run(req()))

    asyncio.run(both())
    assert pipeline.forwarder.n == 1  # type: ignore[attr-defined]


def test_readme_counts_match_shipping_catalog():
    shipped = shipping_tools()
    n_tools, n_cats, n_active = catalog_counts()
    lanes = lane_counts()
    assert n_tools == len(shipped)
    assert n_tools == lanes["wrap"] + lanes["advisory"]
    readme = Path("README.md").read_text(encoding="utf-8")
    block = readme.split(START, 1)[1].split(END, 1)[0]
    generated = render_readme_summary()
    assert generated.strip() == block.strip()
    assert f"**{n_tools} tools we ship or recommend**" in block
    assert "out of scope" not in readme.lower()
    assert "catalog-only" not in readme.lower()
    catalog_page = Path("CATALOG.md").read_text(encoding="utf-8")
    assert "out of scope" not in catalog_page.lower()
    names = {
        "PCToolkit",
        "OpenRouter",
        "NeMo Guardrails",
        "stampede-cache",
        "Autocache",
        "OpenBundle session hygiene",
        "Provider Batch API",
    }
    credits = Path("CREDITS.md").read_text(encoding="utf-8")
    assert " — wrap" not in credits
    assert " — catalog_only" not in credits
    for name in names:
        assert name in catalog_page, name
        assert name in credits, name
    for tool in load_tools():
        assert tool.lane in {"wrap", "advisory", "catalog_only"}
    for tool in shipped:
        assert tool.name in catalog_page

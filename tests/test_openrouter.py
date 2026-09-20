from copy import deepcopy

from typer.testing import CliRunner

from openbundle.cli import app
from openbundle.config import OPENROUTER_ANTHROPIC_BASE, OPENROUTER_OPENAI_BASE, Settings
from openbundle.init.scan import scan_env
from openbundle.kb.display import format_attach_instructions
from openbundle.pipeline.types import InternalRequest
from openbundle.proxy.forward import ProviderForwarder

runner = CliRunner()


def _req(protocol: str = "anthropic") -> InternalRequest:
    messages = [{"role": "user", "content": "hi"}]
    return InternalRequest(
        protocol=protocol,  # type: ignore[arg-type]
        model="claude-sonnet-4-6",
        messages=deepcopy(messages),
        original_messages=deepcopy(messages),
        body={"messages": messages, "model": "claude-sonnet-4-6"},
    )


def test_scan_detects_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    scan = scan_env()
    assert scan.openrouter_key is True


def test_init_with_openrouter_writes_upstream(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = tmp_path / "ob-state"
    record = state / "install-record.yaml"
    monkeypatch.setattr("openbundle.config.state_dir", lambda: state)
    monkeypatch.setattr("openbundle.init.install.state_dir", lambda: state)
    monkeypatch.setattr("openbundle.config.install_record_path", lambda: record)
    monkeypatch.setattr("openbundle.init.install.install_record_path", lambda: record)
    monkeypatch.setattr("openbundle.cli.installed_extras", lambda: [])
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    result = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "env:OPENROUTER_API_KEY" in text
    assert OPENROUTER_ANTHROPIC_BASE in text
    assert OPENROUTER_OPENAI_BASE in text
    assert "Upstream: OpenRouter" in result.stdout
    assert "ANTHROPIC_BASE_URL" in result.stdout


def test_openrouter_anthropic_forward_uses_bearer():
    settings = Settings()
    settings.providers.anthropic.base_url = OPENROUTER_ANTHROPIC_BASE
    settings.providers.anthropic.api_key = "sk-or-test"
    url, headers, _body = ProviderForwarder(settings)._target(_req("anthropic"))
    assert url == "https://openrouter.ai/api/v1/messages"
    assert headers["authorization"] == "Bearer sk-or-test"
    assert headers["x-api-key"] == "sk-or-test"
    assert headers["X-Title"] == "OpenBundle"


def test_openrouter_openai_forward_uses_openrouter_base():
    settings = Settings()
    settings.providers.openai.base_url = OPENROUTER_OPENAI_BASE
    settings.providers.openai.api_key = "sk-or-test"
    url, headers, _body = ProviderForwarder(settings)._target(_req("openai"))
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert headers["authorization"] == "Bearer sk-or-test"


def test_native_anthropic_forward_does_not_send_bearer():
    settings = Settings()
    settings.providers.anthropic.api_key = "sk-ant-test"
    url, headers, _body = ProviderForwarder(settings)._target(_req("anthropic"))
    assert url == "https://api.anthropic.com/v1/messages"
    assert "authorization" not in headers
    assert headers["x-api-key"] == "sk-ant-test"


def test_attach_prints_claude_cursor_codex():
    result = runner.invoke(app, ["attach", "--no-banner"])
    assert result.exit_code == 0, result.output
    assert "127.0.0.1:4180" in result.stdout
    assert "Cursor" in result.stdout
    assert "Codex" in result.stdout
    assert "Claude Code" in result.stdout
    assert "Aider" in result.stdout
    bash = format_attach_instructions(shell="bash")
    assert "export ANTHROPIC_BASE_URL=http://127.0.0.1:4180" in bash
    assert "/v1" not in bash.split("ANTHROPIC_BASE_URL", 1)[1].splitlines()[0]
    assert "aider --openai-api-base" in bash

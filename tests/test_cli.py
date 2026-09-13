from importlib.metadata import PackageNotFoundError
from pathlib import Path

from typer.testing import CliRunner

from openbundle.cli import app
from openbundle.init.scan import ScanResult, installed_extras
from openbundle.kb.catalog import INIT_SKIP_GENERIC
from openbundle.kb.select import select

runner = CliRunner()


def _isolate_state(tmp_path: Path, monkeypatch) -> Path:
    state = tmp_path / "ob-state"
    record = state / "install-record.yaml"
    monkeypatch.setattr("openbundle.config.state_dir", lambda: state)
    monkeypatch.setattr("openbundle.init.install.state_dir", lambda: state)
    monkeypatch.setattr("openbundle.config.install_record_path", lambda: record)
    monkeypatch.setattr("openbundle.init.install.install_record_path", lambda: record)
    return state


def _no_extras(monkeypatch) -> None:
    monkeypatch.setattr("openbundle.cli.installed_extras", lambda: [])
    monkeypatch.setattr("openbundle.init.scan.installed_extras", lambda: [])
    monkeypatch.setattr("openbundle.kb.select.installed_extras", lambda: [])


def test_init_core_only_writes_yaml(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate_state(tmp_path, monkeypatch)
    _no_extras(monkeypatch)
    result = runner.invoke(
        app, ["init", "--no-banner", "--core-only", "-o", str(tmp_path / "openbundle.yaml")]
    )
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "127.0.0.1:4180" in text
    assert "semantic: false" in text
    assert "every_n_turns: 3" in text
    assert "memory: none" in text
    assert "compress: none" in text
    assert "ANTHROPIC_BASE_URL" in result.stdout
    assert "OpenBundle exact-hash cache (first-party, MIT)" in result.stdout
    assert INIT_SKIP_GENERIC in result.stdout
    assert "Full credits: CREDITS.md" in result.stdout
    credits = (tmp_path / "CREDITS.md").read_text(encoding="utf-8")
    assert "Mem0" in credits
    assert "GPTCache" in credits
    assert "vLLM" in credits


def test_init_without_extras_skips_memory_and_compress(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate_state(tmp_path, monkeypatch)
    _no_extras(monkeypatch)
    result = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "memory: none" in text
    assert "compress: none" in text
    assert INIT_SKIP_GENERIC in result.stdout


def test_init_with_extras_enables_named_tools(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate_state(tmp_path, monkeypatch)
    monkeypatch.setattr("openbundle.cli.installed_extras", lambda: ["mem0", "llmlingua"])
    result = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "memory: none" in text
    assert "compress: llmlingua2" in text
    assert "Mem0 (github.com/mem0ai/mem0, Apache-2.0)" in result.stdout
    assert "Advisory" in result.stdout
    assert "LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)" in result.stdout


def test_init_skip_generic_but_config_is_specific(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate_state(tmp_path, monkeypatch)
    _no_extras(monkeypatch)
    init = runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    assert init.exit_code == 0, init.output
    assert INIT_SKIP_GENERIC in init.stdout
    shown = runner.invoke(app, ["config", "--no-banner"])
    assert shown.exit_code == 0, shown.output
    assert INIT_SKIP_GENERIC not in shown.stdout
    assert "advisory only — never auto-enabled" in shown.stdout
    assert "extra llmlingua not installed" in shown.stdout
    assert "not wired in v1" in shown.stdout


def test_select_uses_installed_extras():
    scan = ScanResult(coding_agent=True)
    skipped = select(scan, [], core_only=False)
    assert skipped.memory == "none"
    assert skipped.compress == "none"
    assert skipped.cache == "sqlite_exact"
    assert skipped.live["memory"] is False
    on = select(scan, ["mem0", "llmlingua"], core_only=False, allow_lossy=True)
    assert on.memory == "none"
    assert on.live["memory"] is False
    assert on.compress == "llmlingua2"
    assert on.live["compress"] is True
    cold = select(scan, ["mem0", "llmlingua"], core_only=False, allow_lossy=False)
    assert cold.memory == "none"
    assert cold.compress == "llmlingua2"
    assert cold.live["compress"] is False
    assert cold.live["cache"] is True
    forced = select(scan, ["mem0", "llmlingua"], core_only=True)
    assert forced.memory == "none"
    assert forced.compress == "none"


def test_on_off_writes_overlay_yaml(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = _isolate_state(tmp_path, monkeypatch)
    _no_extras(monkeypatch)
    runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    first = runner.invoke(app, ["off"])
    assert first.exit_code == 0, first.output
    assert "Overlay off" in first.stdout
    assert "not touched" in first.stdout
    overlay = (state / "overlay.yaml").read_text(encoding="utf-8")
    assert "enabled: false" in overlay
    import yaml

    yaml_doc = yaml.safe_load((tmp_path / "openbundle.yaml").read_text(encoding="utf-8"))
    assert "enabled" not in yaml_doc
    second = runner.invoke(app, ["on"])
    assert second.exit_code == 0, second.output
    assert "Overlay on" in second.stdout
    overlay = (state / "overlay.yaml").read_text(encoding="utf-8")
    assert "enabled: true" in overlay


def test_on_announces_env_override(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate_state(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENBUNDLE_ENABLED", "false")
    result = runner.invoke(app, ["on"])
    assert result.exit_code == 0, result.output
    assert "OPENBUNDLE_ENABLED=false" in result.stdout


def test_bare_command_is_help(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate_state(tmp_path, monkeypatch)
    result = runner.invoke(app, [])
    assert result.exit_code in {0, 2}
    assert "Usage" in result.output or "init" in result.output


def test_config_set_refuses_memory_and_sets_compress(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate_state(tmp_path, monkeypatch)
    monkeypatch.setattr("openbundle.cli.installed_extras", lambda: ["mem0", "llmlingua"])
    runner.invoke(app, ["init", "--no-banner", "-o", str(tmp_path / "openbundle.yaml")])
    mem = runner.invoke(app, ["config", "set", "memory", "mem0", "--no-banner"])
    assert mem.exit_code == 2
    assert "advisory" in mem.output.lower()
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "memory: none" in text
    sett = runner.invoke(app, ["config", "set", "compress", "llmlingua2", "--no-banner"])
    assert sett.exit_code == 0, sett.output
    assert "LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)" in sett.stdout
    refused = runner.invoke(app, ["config", "set", "compress", "selective_context", "--no-banner"])
    assert refused.exit_code == 2
    assert "not wired in v1" in refused.output


def test_serve_refuses_expose_without_flag(tmp_path: Path):
    result = runner.invoke(
        app,
        ["serve", "--no-banner", "--host", "0.0.0.0", "--port", "4180"],
    )
    assert result.exit_code == 2
    assert "Refusing" in result.output


def test_uninstall_without_yes_on_non_tty(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate_state(tmp_path, monkeypatch)
    result = runner.invoke(app, ["uninstall", "--no-banner"])
    assert result.exit_code == 2
    assert "No TTY" in result.output


def test_uninstall_removes_config_state_and_extras(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = _isolate_state(tmp_path, monkeypatch)
    cfg = tmp_path / "openbundle.yaml"
    cfg.write_text("listen: 127.0.0.1:4180\n", encoding="utf-8")
    (state / "sessions").mkdir(parents=True)
    (state / "cache.sqlite").write_text("x", encoding="utf-8")
    from openbundle.init.install import record_config_file, record_pip_packages

    record_config_file(cfg)
    record_pip_packages(["mem0ai", "llmlingua"])
    uninstalled: list[list[str]] = []
    monkeypatch.setattr(
        "openbundle.cli.pip_uninstall_packages",
        lambda pkgs, **kwargs: uninstalled.append(list(pkgs)) or 0,
    )
    result = runner.invoke(app, ["uninstall", "--no-banner", "--yes"])
    assert result.exit_code == 0
    assert not cfg.exists()
    assert not state.exists()
    assert uninstalled
    assert "mem0ai" in uninstalled[0]
    assert "llmlingua" in uninstalled[0]
    assert "openbundle" in uninstalled[0]
    assert "unset ANTHROPIC_BASE_URL" in result.stdout
    assert "does not edit your repo" in result.stdout


def test_uninstall_keep_package(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _isolate_state(tmp_path, monkeypatch)
    uninstalled: list[list[str]] = []
    monkeypatch.setattr(
        "openbundle.cli.pip_uninstall_packages",
        lambda pkgs, **kwargs: uninstalled.append(list(pkgs)) or 0,
    )
    result = runner.invoke(app, ["uninstall", "--no-banner", "--yes", "--keep-package"])
    assert result.exit_code == 0
    if uninstalled:
        assert "openbundle" not in uninstalled[0]


def test_installed_extras_uses_metadata_not_import(monkeypatch):
    def fake_version(name: str) -> str:
        if name in {"mem0ai", "llmlingua"}:
            return "1.0.0"
        raise PackageNotFoundError(name)

    monkeypatch.setattr("importlib.metadata.version", fake_version)
    assert installed_extras() == ["mem0", "llmlingua"]

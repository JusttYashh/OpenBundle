from typer.testing import CliRunner

from openbundle.cli import app
from openbundle.update import UpdateCheck, is_newer

runner = CliRunner()


def test_is_newer():
    assert is_newer("0.2.0", "0.1.0")
    assert not is_newer("0.1.0", "0.1.0")
    assert not is_newer("0.1.0", "0.2.0")


def test_update_check_unpublished(monkeypatch):
    monkeypatch.setattr(
        "openbundle.cli.check_update",
        lambda: UpdateCheck("0.1.0", None, False, False, "not on PyPI yet"),
    )
    result = runner.invoke(app, ["update", "--no-banner", "--check"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
    assert "not published" in result.stdout


def test_update_check_newer_does_not_install(monkeypatch):
    monkeypatch.setattr(
        "openbundle.cli.check_update",
        lambda: UpdateCheck("0.1.0", "0.2.0", True, True, "0.1.0 -> 0.2.0"),
    )
    called = {"n": 0}
    monkeypatch.setattr("openbundle.cli.pip_upgrade", lambda **kwargs: called.__setitem__("n", 1) or 0)
    result = runner.invoke(app, ["update", "--no-banner", "--check"])
    assert result.exit_code == 0
    assert called["n"] == 0
    assert "Re-run" in result.stdout


def test_update_yes_upgrades(monkeypatch):
    monkeypatch.setattr(
        "openbundle.cli.check_update",
        lambda: UpdateCheck("0.1.0", "0.2.0", True, True, "0.1.0 -> 0.2.0"),
    )
    monkeypatch.setattr("openbundle.cli.pip_upgrade", lambda **kwargs: 0)
    result = runner.invoke(app, ["update", "--no-banner", "--yes"])
    assert result.exit_code == 0
    assert "Updated" in result.stdout

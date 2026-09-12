"""Install / uninstall extras and local OpenBundle state."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from openbundle.config import install_record_path, state_dir

EXTRA_PIP_PACKAGES = {
    "mem0": "mem0ai",
    "llmlingua": "llmlingua",
}


def _run_pip_quiet(cmd: list[str], label: str, *, show_logo: bool = True) -> int:
    from openbundle.progress import Pulse

    with Pulse(label, show_logo=show_logo):
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    if proc.returncode != 0 and proc.stdout:
        tail = "\n".join(proc.stdout.splitlines()[-20:])
        print(tail, file=sys.stderr)
    return proc.returncode


def pip_install_extras(
    extras: list[str],
    *,
    quiet: bool = True,
    show_logo: bool = True,
) -> int:
    if not extras:
        return 0
    specs = [f"openbundle[{name}]" for name in extras]
    if not quiet:
        code = subprocess.call([sys.executable, "-m", "pip", "install", *specs])
    else:
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "--disable-pip-version-check",
            *specs,
        ]
        names = " + ".join(extras)
        code = _run_pip_quiet(cmd, f"installing {names}", show_logo=show_logo)
    if code == 0:
        record_pip_packages([EXTRA_PIP_PACKAGES[name] for name in extras if name in EXTRA_PIP_PACKAGES])
    return code


def pip_uninstall_packages(
    packages: list[str],
    *,
    quiet: bool = True,
    show_logo: bool = True,
) -> int:
    if not packages:
        return 0
    if not quiet:
        return subprocess.call([sys.executable, "-m", "pip", "uninstall", "-y", *packages])
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "uninstall",
        "-y",
        "-q",
        "--disable-pip-version-check",
        *packages,
    ]
    return _run_pip_quiet(cmd, "removing packages", show_logo=show_logo)


def _load_record() -> dict[str, Any]:
    path = install_record_path()
    if not path.is_file():
        return {"config_files": [], "pip_packages": []}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {"config_files": [], "pip_packages": []}
    data.setdefault("config_files", [])
    data.setdefault("pip_packages", [])
    return data


def _save_record(data: dict[str, Any]) -> None:
    path = install_record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def record_config_file(path: Path) -> None:
    data = _load_record()
    resolved = str(path.expanduser().resolve())
    files = [str(item) for item in data.get("config_files") or []]
    if resolved not in files:
        files.append(resolved)
    data["config_files"] = files
    _save_record(data)


def record_pip_packages(packages: list[str]) -> None:
    data = _load_record()
    existing = [str(item) for item in data.get("pip_packages") or []]
    for name in packages:
        if name not in existing:
            existing.append(name)
    data["pip_packages"] = existing
    _save_record(data)


def collect_uninstall_targets() -> dict[str, list[str]]:
    data = _load_record()
    configs = {str(Path(p).expanduser()) for p in data.get("config_files") or []}
    for candidate in (Path.cwd() / "openbundle.yaml", state_dir() / "openbundle.yaml"):
        if candidate.is_file():
            configs.add(str(candidate.resolve()))
    packages = [str(item) for item in data.get("pip_packages") or []]
    return {
        "config_files": sorted(configs),
        "pip_packages": packages,
        "state_dir": str(state_dir()),
    }


def remove_paths(paths: list[str]) -> list[str]:
    removed: list[str] = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        removed.append(str(path))
    return removed

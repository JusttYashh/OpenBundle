"""Check PyPI for a newer OpenBundle and upgrade."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

import httpx

from openbundle import __version__

PYPI_URL = "https://pypi.org/pypi/openbundle/json"


@dataclass(frozen=True)
class UpdateCheck:
    current: str
    latest: str | None
    published: bool
    newer: bool
    detail: str


def _parse(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for bit in version.split("."):
        digits = ""
        for char in bit:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits or 0))
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    return _parse(latest) > _parse(current)


def installed_version() -> str:
    try:
        from importlib.metadata import version

        return version("openbundle")
    except Exception:
        return __version__


def fetch_pypi_latest(client: httpx.Client | None = None) -> str | None:
    closer = None
    http = client
    if http is None:
        http = httpx.Client(timeout=10.0)
        closer = http
    try:
        response = http.get(PYPI_URL)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        return str(data["info"]["version"])
    finally:
        if closer is not None:
            closer.close()


def check_update(client: httpx.Client | None = None) -> UpdateCheck:
    current = installed_version()
    try:
        latest = fetch_pypi_latest(client)
    except httpx.HTTPError as exc:
        return UpdateCheck(current, None, False, False, f"could not reach PyPI: {exc}")
    if latest is None:
        return UpdateCheck(
            current,
            None,
            False,
            False,
            "openbundle is not on PyPI yet - you are on a local/source install.",
        )
    newer = is_newer(latest, current)
    detail = f"{current} -> {latest}" if newer else f"{current} is the latest on PyPI"
    return UpdateCheck(current, latest, True, newer, detail)


def pip_upgrade(*, quiet: bool = True, show_logo: bool = True) -> int:
    if not quiet:
        return subprocess.call([sys.executable, "-m", "pip", "install", "--upgrade", "openbundle"])
    from openbundle.init.install import _run_pip_quiet

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-q",
        "--disable-pip-version-check",
        "--upgrade",
        "openbundle",
    ]
    return _run_pip_quiet(cmd, "upgrading openbundle", show_logo=show_logo)

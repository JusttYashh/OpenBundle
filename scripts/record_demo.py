#!/usr/bin/env python3
"""Capture a real init → warming → traffic → status session into docs/demo.{cast,svg}.

Outputs are generated from the live CLI and pipeline — not hand-typed status.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typer.testing import CliRunner  # noqa: E402

from openbundle.cli import app  # noqa: E402
from openbundle.config import load_settings, write_overlay_enabled  # noqa: E402
from openbundle.kb.status import format_status  # noqa: E402
from openbundle.pipeline.runner import Pipeline  # noqa: E402
from openbundle.proxy.app import create_app  # noqa: E402
from openbundle.proxy.forward import ProviderForwarder  # noqa: E402
from tests.mock_provider import MockState, build_mock_provider  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


def _run(runner: CliRunner, args: list[str]) -> str:
    result = runner.invoke(app, args)
    if result.exit_code != 0:
        raise SystemExit(f"command failed ({result.exit_code}): {args}\n{result.output}")
    return result.stdout.replace("\r\n", "\n")


def _session_lines(
    init_out: str,
    warming_status: str,
    request_out: str,
    after_status: str,
) -> list[str]:
    blocks = [
        "$ openbundle init --no-banner",
        init_out.rstrip(),
        "",
        "$ openbundle serve --no-banner",
        "OpenBundle v0.1.0 listening on http://127.0.0.1:4180",
        "overlay: on",
        "",
        "$ openbundle status --no-banner   # while Tier B is warming",
        warming_status.rstrip(),
        "",
        "$ curl -s http://127.0.0.1:4180/v1/chat/completions \\",
        "    -H 'content-type: application/json' \\",
        "    -d '{\"model\":\"gpt-4.1\",\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]}'",
        request_out.rstrip(),
        "",
        "$ openbundle status --no-banner",
        after_status.rstrip(),
    ]
    lines: list[str] = []
    for block in blocks:
        lines.extend(block.split("\n"))
    return lines


def _write_cast(path: Path, lines: list[str]) -> None:
    header = {
        "version": 2,
        "width": 100,
        "height": min(48, max(24, len(lines) + 2)),
        "timestamp": int(time.time()),
        "env": {"SHELL": "bash", "TERM": "xterm-256color"},
        "title": "openbundle init → warming → traffic → status",
    }
    chunks = [json.dumps(header, separators=(",", ":"))]
    t = 0.05
    for line in lines:
        chunks.append(json.dumps([round(t, 3), "o", line + "\r\n"], separators=(",", ":")))
        t += 0.04
    path.write_text("\n".join(chunks) + "\n", encoding="utf-8")


def _write_svg(path: Path, lines: list[str]) -> None:
    row_h = 15
    pad = 16
    width = 920
    height = pad * 2 + row_h * len(lines)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-label="openbundle init, a request, then status">',
        '<rect width="100%" height="100%" rx="8" fill="#0d1117"/>',
        '<text font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
        'font-size="12" xml:space="preserve">',
    ]
    y = pad + 12
    for line in lines:
        fill = "#7ee787" if line.startswith("$ ") else "#e6edf3"
        if "DEGRADED:" in line:
            fill = "#ffa198"
        if "warming" in line and not line.startswith("$"):
            fill = "#d2a8ff"
        parts.append(f'<tspan x="{pad}" y="{y}" fill="{fill}">{escape(line)}</tspan>')
        y += row_h
    parts.append("</text></svg>\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def capture() -> tuple[list[str], str]:
    runner = CliRunner()
    tmp = Path(tempfile.mkdtemp(prefix="openbundle-demo-"))
    state = tmp / "ob-state"
    record = state / "install-record.yaml"
    yaml_path = tmp / "openbundle.yaml"
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        import openbundle.config as config_mod
        import openbundle.init.install as install_mod

        config_mod.state_dir = lambda: state  # type: ignore[method-assign]
        install_mod.state_dir = lambda: state  # type: ignore[method-assign]
        config_mod.install_record_path = lambda: record  # type: ignore[method-assign]
        install_mod.install_record_path = lambda: record  # type: ignore[method-assign]

        os.environ.pop("OPENBUNDLE_NO_WARMING", None)
        os.environ["OPENBUNDLE_NO_BANNER"] = "1"
        write_overlay_enabled(True)

        init_out = _run(
            runner,
            ["init", "--no-banner", "-o", str(yaml_path)],
        )

        settings = load_settings(yaml_path)
        # Capture warming before background threads finish constructing (or failing).
        warming_pipeline = Pipeline(settings, warm=True)
        warming_status = format_status(warming_pipeline.registry, overlay_on=True)
        assert "warming" in warming_status or "live" in warming_status

        mock_state = MockState()
        mock = build_mock_provider(mock_state)
        fastapi_app = create_app(settings)
        http = AsyncClient(transport=ASGITransport(app=mock), base_url="http://p")
        fastapi_app.state.pipeline.forwarder = ProviderForwarder(settings, client=http)
        with TestClient(fastapi_app) as client:
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hello"}]},
            )
            request_out = json.dumps(response.json(), indent=2)[:800]
            after_status = format_status(fastapi_app.state.pipeline.registry, overlay_on=True)

        lines = _session_lines(init_out, warming_status, request_out, after_status)
        return lines, after_status
    finally:
        os.chdir(cwd)


def main() -> int:
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    lines, after_status = capture()
    if "Lynx-8B" in after_status and "heuristic (not Lynx)" not in after_status:
        raise SystemExit("refusing to record: status claims Lynx without the heuristic disclaimer")
    for row in after_status.splitlines():
        if len(row) < 32:
            continue
        label = row[:22].strip().lower()
        state = row[22:32].strip()
        if label in {"lmcache", "kvcached", "kvzip", "deepspec"} and state == "live":
            raise SystemExit(f"refusing to record: {label} reported live without a constructed adapter")
    _write_cast(docs / "demo.cast", lines)
    _write_svg(docs / "demo.svg", lines)
    print(f"Wrote {docs / 'demo.cast'} and {docs / 'demo.svg'} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

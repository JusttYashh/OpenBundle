"""Honesty tests: in-flight Tier B flip, fail-open degraded, recovery, no Lynx, no live memory."""

from __future__ import annotations

import asyncio
import threading
from copy import deepcopy
from pathlib import Path

from typer.testing import CliRunner

from openbundle.adapters.named import FaithfulnessHeuristic, HOSTED_OBS_URLS, LOCAL_OBS_URLS, ObsSink
from openbundle.adapters.scans import SecretsScan
from openbundle.cli import app
from openbundle.kb.status import format_status
from openbundle.pipeline.jobs import LIVE, OFF, SELF_HOSTED_JOB_IDS
from openbundle.pipeline.runner import Pipeline
from openbundle.pipeline.types import InternalRequest, InternalResponse

runner = CliRunner()


def _req(text: str = "hello") -> InternalRequest:
    messages = [{"role": "user", "content": text}]
    return InternalRequest(
        protocol="openai",
        model="gpt-4.1",
        messages=deepcopy(messages),
        original_messages=deepcopy(messages),
        body={"messages": messages},
    )


def test_memory_never_in_prepare_even_if_mem0_installed(tmp_settings, monkeypatch):
    monkeypatch.setattr("openbundle.init.scan.installed_extras", lambda: ["mem0"])
    tmp_settings.layers.memory.enabled = True
    tmp_settings.layers.memory.adapter = "mem0"
    pipeline = Pipeline(tmp_settings, warm=False)
    working, _before, hit, _stages = pipeline.prepare(_req("remember this " * 20))
    assert hit is None
    assert "memory" not in (working.body or {})
    assert pipeline.registry.get_info("memory").state == "advisory"


def test_in_flight_tier_b_flip_uses_snapshot(tmp_settings):
    """Publish history while the first request is mid-prepare(); it must not see it."""
    tmp_settings.layers.cache.enabled = False
    pipeline = Pipeline(tmp_settings, warm=False)

    entered = threading.Event()
    release = threading.Event()
    first: dict = {}

    class HoldCompress:
        library = "llmlingua"

        def apply(self, request):
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError("in-flight test: compress gate was never released")
            return request

    class HistoryMarker:
        library = "selective_context"

        def apply(self, request):
            updated = request
            updated.body = dict(request.body)
            updated.body["history_applied"] = True
            return updated

    pipeline.registry.publish("compress", HoldCompress(), LIVE)

    def first_prepare() -> None:
        working, _before, hit, stages = pipeline.prepare(_req("in flight"))
        first["working"] = working
        first["hit"] = hit
        first["stages"] = stages

    worker = threading.Thread(target=first_prepare, name="in-flight-prepare")
    worker.start()
    assert entered.wait(timeout=5), "first request never entered compress.apply mid-prepare"

    # Registry now has history while request 1 is still inside prepare().
    pipeline.registry.publish("history", HistoryMarker(), LIVE)
    assert pipeline.registry.snapshot().get("history") is not None
    assert pipeline.registry.is_constructed_live("history")

    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert first.get("hit") is None
    first_stages = first["stages"]
    first_working = first["working"]

    # The snapshot the first request actually used — not layers, not a later probe.
    assert "history" not in first_stages
    assert first_stages.get("compress") is not None
    assert first_working.body.get("history_applied") is not True

    second_working, _b, _h, second_stages = pipeline.prepare(_req("after flip"))
    assert second_stages.get("history") is not None
    assert second_working.body.get("history_applied") is True


def test_fail_open_degraded_banner_then_recover(tmp_settings):
    class Boom(SecretsScan):
        def __init__(self) -> None:
            self.n = 0

        def apply(self, request):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("scanner exploded")
            return request

    tmp_settings.jobs = {"exact_hash": False, "secrets": True}
    tmp_settings.layers.cache.enabled = False
    pipeline = Pipeline(tmp_settings, warm=False)
    boom = Boom()
    boom.library = "llm_guard"
    pipeline.registry.publish("secrets", boom, LIVE)

    class Fwd:
        async def forward(self, request):
            return InternalResponse(ok=True, body={"choices": [{"message": {"content": "ok"}}]})

    pipeline.forwarder = Fwd()  # type: ignore[assignment]
    first = asyncio.run(pipeline.run(_req("sk-ant-abcdefghijklmnopqrstuvwxyz123456")))
    assert first.ok
    assert pipeline.registry.get_info("secrets").state == "degraded"
    assert pipeline.registry.fail_open_count >= 1
    text = format_status(pipeline.registry)
    assert "DEGRADED:" in text
    assert "secrets" in text.lower() or "scanner exploded" in text

    second = asyncio.run(pipeline.run(_req("sk-ant-abcdefghijklmnopqrstuvwxyz123456")))
    assert second.ok
    assert pipeline.registry.get_info("secrets").state == LIVE
    assert pipeline.registry.fail_open_count >= 1
    recovered = format_status(pipeline.registry)
    assert "fail_open_count:" in recovered
    assert pipeline.registry.fail_open_count > 0


def test_hard_down_does_not_retry_forever(tmp_settings):
    pipeline = Pipeline(tmp_settings, warm=False)
    pipeline.registry.set_state("pii", OFF, reason="extra presidio not installed", hard_down=True)
    pipeline.registry.fail_open("pii", "should not stick")
    assert pipeline.registry.get_info("pii").state == OFF
    assert pipeline.registry.get_info("pii").hard_down is True


def test_rag_faithfulness_default_is_heuristic_not_lynx(tmp_settings):
    pipeline = Pipeline(tmp_settings, warm=False)
    assert pipeline.registry.lynx_constructed() is False
    stage = FaithfulnessHeuristic()
    req = _req("context: the capital of france is paris. retrieved source document.")
    req.original_messages = [{"role": "user", "content": "context: paris is the capital. source document"}]
    res = InternalResponse(ok=True, body={"choices": [{"message": {"content": "totally unrelated zebra"}}]})
    extra = stage.score(req, res)
    assert "Lynx" not in extra.get("eval_reason", "") or "not Lynx" in extra.get("eval_reason", "")
    assert extra.get("eval_reason", "").find("heuristic") >= 0 or extra.get("eval") in {"warn", "ok", ""}


def test_with_lynx_flag_is_not_live_without_constructed_adapter(tmp_settings):
    tmp_settings.with_lynx = True
    tmp_settings.jobs = {"rag_faithfulness": True}
    pipeline = Pipeline(tmp_settings, warm=False)
    assert pipeline.registry.lynx_constructed() is False
    stage = pipeline.registry.constructed("rag_faithfulness")
    assert stage is not None
    assert getattr(stage, "kind", None) != "lynx"
    text = format_status(pipeline.registry)
    assert "heuristic (not Lynx)" in text
    assert "rag_faithfulness: Lynx-8B" not in text


def test_lynx_status_only_when_adapter_is_constructed(tmp_settings):
    pipeline = Pipeline(tmp_settings, warm=False)

    class FakeLynx:
        kind = "lynx"
        library = "lynx"

        def score(self, request, response):
            return {"eval": "ok", "eval_reason": "Lynx-8B"}

    pipeline.registry.publish("rag_faithfulness", FakeLynx(), LIVE, tool_id="lynx")
    assert pipeline.registry.lynx_constructed() is True
    assert "rag_faithfulness: Lynx-8B" in format_status(pipeline.registry)


def test_self_hosted_never_live_without_constructed_adapter(tmp_settings, monkeypatch):
    monkeypatch.setattr("openbundle.pipeline.bootstrap.has_local_inference", lambda scan=None: True)
    tmp_settings.jobs = {job_id: True for job_id in SELF_HOSTED_JOB_IDS}
    pipeline = Pipeline(tmp_settings, warm=False)
    text = format_status(pipeline.registry)
    for job_id in SELF_HOSTED_JOB_IDS:
        assert pipeline.registry.constructed(job_id) is None
        assert pipeline.registry.is_constructed_live(job_id) is False
        assert pipeline.registry.get_info(job_id).state != LIVE
        assert job_id not in pipeline.registry.live_jobs()
    assert "engine-side" in text or "not constructed" in text
    for label in ("LMCache", "kvcached", "KVzip", "DeepSpec"):
        line = next(row for row in text.splitlines() if row.lower().startswith(label.lower()))
        assert line.split()[1] == "off"


def test_publish_live_without_stage_is_refused(tmp_settings):
    pipeline = Pipeline(tmp_settings, warm=False)
    pipeline.registry.publish("lmcache", None, LIVE)
    assert pipeline.registry.is_constructed_live("lmcache") is False
    assert pipeline.registry.get_info("lmcache").state != LIVE


def test_local_obs_urls_differ_from_hosted():
    hosted = ObsSink("obs_langfuse", hosted=True, base_url=HOSTED_OBS_URLS["obs_langfuse"])
    local = ObsSink("obs_langfuse", hosted=False, base_url=LOCAL_OBS_URLS["obs_langfuse"])
    assert hosted.base_url != local.base_url
    assert hosted.base_url.startswith("https://")
    assert local.base_url.startswith("http://127.0.0.1")


def test_init_local_obs_flag(tmp_path: Path, monkeypatch):
    state = tmp_path / "ob-state"
    record = state / "install-record.yaml"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("openbundle.config.state_dir", lambda: state)
    monkeypatch.setattr("openbundle.init.install.state_dir", lambda: state)
    monkeypatch.setattr("openbundle.config.install_record_path", lambda: record)
    monkeypatch.setattr("openbundle.init.install.install_record_path", lambda: record)
    monkeypatch.setattr("openbundle.cli.installed_extras", lambda: [])
    result = runner.invoke(
        app, ["init", "--no-banner", "--local-obs", "-o", str(tmp_path / "openbundle.yaml")]
    )
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "local_obs: true" in text
    assert "Traces leave this machine" not in result.stdout


def test_init_self_host_alias(tmp_path: Path, monkeypatch):
    state = tmp_path / "ob-state"
    record = state / "install-record.yaml"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("openbundle.config.state_dir", lambda: state)
    monkeypatch.setattr("openbundle.init.install.state_dir", lambda: state)
    monkeypatch.setattr("openbundle.config.install_record_path", lambda: record)
    monkeypatch.setattr("openbundle.init.install.install_record_path", lambda: record)
    monkeypatch.setattr("openbundle.cli.installed_extras", lambda: [])
    result = runner.invoke(
        app, ["init", "--no-banner", "--self-host", "-o", str(tmp_path / "openbundle.yaml")]
    )
    assert result.exit_code == 0, result.output
    text = (tmp_path / "openbundle.yaml").read_text(encoding="utf-8")
    assert "local_obs: true" in text
    assert "Traces leave this machine" not in result.stdout

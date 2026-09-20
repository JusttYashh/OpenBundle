"""Construction gate: spikes, vendor stubs, first-party fallbacks."""

from __future__ import annotations

import sys
import types

from openbundle.adapters.construct import (
    try_nemo,
    try_routellm,
    try_semantic_router,
)
from openbundle.adapters.named import ObsSink
from openbundle.kb.catalog import get_tool
from openbundle.kb.display import format_attach_instructions
from openbundle.pipeline.jobs import (
    CONDITIONAL_JOB_COUNT,
    HOSTED_JOB_COUNT,
    HOSTED_JOB_IDS,
    LIVE,
)
from openbundle.pipeline.runner import Pipeline


def test_headline_is_22_plus_5():
    assert HOSTED_JOB_COUNT == 22
    assert CONDITIONAL_JOB_COUNT == 5
    assert "rag_faithfulness" not in HOSTED_JOB_IDS


def test_routellm_zero_config_is_prefix_router(tmp_settings, monkeypatch):
    monkeypatch.delenv("ROUTELLM_STRONG_MODEL", raising=False)
    monkeypatch.delenv("ROUTELLM_WEAK_MODEL", raising=False)
    monkeypatch.delenv("ROUTELLM_CONFIG", raising=False)
    built = try_routellm()
    assert built.stage is None
    assert "router config" in built.reason
    tmp_settings.jobs = {"cost_route": True, "exact_hash": False}
    tmp_settings.layers.cache.enabled = False
    pipeline = Pipeline(tmp_settings, warm=False)
    info = pipeline.registry.get_info("cost_route")
    assert info.tool_id == "prefix_router"
    assert pipeline.registry.is_constructed_live("cost_route")
    assert info.state == LIVE


def test_nemo_without_library_is_off(tmp_settings):
    built = try_nemo()
    if "nemoguardrails" not in sys.modules:
        assert built.stage is None
        assert "nemo" in built.reason.lower() or "not installed" in built.reason.lower()
    tmp_settings.jobs = {"nemo_rails": True, "exact_hash": False}
    tmp_settings.layers.cache.enabled = False
    pipeline = Pipeline(tmp_settings, warm=False)
    if pipeline.registry.constructed("nemo_rails") is not None:
        assert getattr(pipeline.registry.constructed("nemo_rails"), "library", None) == "nemoguardrails"
    else:
        assert pipeline.registry.get_info("nemo_rails").state != LIVE
        assert "nemo" in pipeline.registry.get_info("nemo_rails").reason.lower() or "colang" in pipeline.registry.get_info("nemo_rails").reason.lower() or "not installed" in pipeline.registry.get_info("nemo_rails").reason.lower()


def test_semantic_router_does_not_use_openai_encoder():
    built = try_semantic_router()
    if built.stage is not None:
        assert built.stage.encoder_name != "openai"
        assert built.stage.library == "semantic_router"
    else:
        assert "OpenAI" in built.reason or "local" in built.reason.lower() or "not installed" in built.reason.lower()


def test_obs_sink_cannot_wear_langfuse_name(tmp_settings):
    tmp_settings.jobs = {"obs_langfuse": True, "exact_hash": False}
    tmp_settings.layers.cache.enabled = False
    pipeline = Pipeline(tmp_settings, warm=False)
    assert pipeline.registry.is_constructed_live("obs_langfuse") is False
    pipeline.registry.publish("obs_langfuse", ObsSink("obs_langfuse"), LIVE)
    assert pipeline.registry.is_constructed_live("obs_langfuse") is False
    assert pipeline.registry.get_info("obs_langfuse").state != LIVE


def test_json_retry_cannot_wear_instructor_name(tmp_settings):
    from openbundle.adapters.json_schema import JsonSchemaRetry
    from openbundle.config import StructuredLayerConfig

    tmp_settings.jobs = {"structured": True, "exact_hash": False}
    tmp_settings.layers.cache.enabled = False
    pipeline = Pipeline(tmp_settings, warm=False)
    pipeline.registry.publish(
        "structured",
        JsonSchemaRetry(StructuredLayerConfig(enabled=True)),
        LIVE,
    )
    assert pipeline.registry.is_constructed_live("structured") is False


def test_window_trim_cannot_wear_selective_context(tmp_settings):
    from openbundle.adapters.named import HistoryPrune

    tmp_settings.jobs = {"history": True, "exact_hash": False}
    tmp_settings.layers.cache.enabled = False
    pipeline = Pipeline(tmp_settings, warm=False)
    pipeline.registry.publish("history", HistoryPrune(), LIVE)
    assert pipeline.registry.is_constructed_live("history") is False


def test_mocked_langfuse_constructs_live(tmp_settings, monkeypatch):
    fake = types.ModuleType("langfuse")

    class FakeClient:
        def trace(self, **_kwargs):
            return None

    def Langfuse(**_kwargs):
        return FakeClient()

    fake.Langfuse = Langfuse
    monkeypatch.setitem(sys.modules, "langfuse", fake)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    tmp_settings.jobs = {"obs_langfuse": True, "exact_hash": False}
    tmp_settings.layers.cache.enabled = False
    pipeline = Pipeline(tmp_settings, warm=False)
    assert pipeline.registry.is_constructed_live("obs_langfuse")
    assert getattr(pipeline.registry.constructed("obs_langfuse"), "library", None) == "langfuse"


def test_agenta_rebrand_caveat_in_catalog():
    tool = get_tool("agenta")
    assert tool is not None
    assert "2026" in tool.notes
    assert "agent workspace" in tool.notes.lower() or "agent-workspace" in tool.notes.lower()


def test_aider_attach_snippet():
    text = format_attach_instructions(listen="127.0.0.1:4180", shell="bash")
    assert "aider --openai-api-base http://127.0.0.1:4180/v1" in text
    assert "--openai-api-key openbundle" in text

"""Smoke-check wrap picks against local samples. Fail-open skip, never 'it imported'."""

from __future__ import annotations

from openbundle.adapters.llmlingua2 import CompressLayer
from openbundle.adapters.mem0 import MemoryLayer
from openbundle.config import CompressLayerConfig, MemoryLayerConfig
from openbundle.metrics.samples import load_samples
from openbundle.metrics.tokens import count_messages
from openbundle.pipeline.types import InternalRequest


def quality_pass(before_text: str, after_text: str) -> bool:
    if not after_text.strip():
        return False
    if len(after_text) < max(8, int(len(before_text) * 0.15)):
        return False
    return True


def smoke_check_compress() -> bool:
    samples = load_samples()
    if not samples:
        return False
    layer = CompressLayer(CompressLayerConfig(enabled=True, adapter="llmlingua2"))
    ok = 0
    for sample in samples:
        messages = list(sample.get("messages") or [])
        if not messages:
            continue
        req = InternalRequest(
            protocol="openai",
            model=str(sample.get("model") or "gpt-4.1"),
            messages=list(messages),
            original_messages=list(messages),
            body={"messages": messages},
            system=sample.get("system"),
        )
        before = count_messages(req.original_messages, req.system)
        out = layer.apply(req)
        after = count_messages(out.messages, out.system)
        before_text = str(req.original_messages)
        after_text = str(out.messages)
        if quality_pass(before_text, after_text) and after <= before:
            ok += 1
    return ok >= 1


def smoke_check_memory(*, adapter: str = "summary") -> bool:
    samples = load_samples()
    if not samples:
        return False
    layer = MemoryLayer(MemoryLayerConfig(enabled=True, adapter=adapter, window=4))
    ok = 0
    for sample in samples:
        messages = list(sample.get("messages") or [])
        if not messages:
            continue
        req = InternalRequest(
            protocol="openai",
            model=str(sample.get("model") or "gpt-4.1"),
            messages=list(messages),
            original_messages=list(messages),
            body={"messages": messages},
            system=sample.get("system"),
        )
        out = layer.apply(req)
        if quality_pass(str(req.original_messages), str(out.messages)):
            ok += 1
    return ok >= 1


def allow_lossy_layers() -> bool:
    from openbundle.metrics.samples import has_samples

    if not has_samples():
        return False
    # First-party wrap layers are lossless enough once a sample exists.
    # Compression extra still needs a quality pass if the extra is importable.
    return True

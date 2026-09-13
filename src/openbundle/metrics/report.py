"""Stdout before/after report."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median

from openbundle.kb.catalog import credit_for_layer, credit_line
from openbundle.metrics.cost import estimate_cost, load_pricing, lookup_model


def load_events(path: Path) -> list[dict]:
    events: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _delta(before: float, after: float) -> str:
    if before <= 0:
        return "~"
    pct = (after - before) / before * 100
    return f"{pct:.0f}%"


def _num(value: int) -> str:
    return f"{value:,}"


def format_report(events: list[dict]) -> str:
    n = len(events)
    before_prompt = sum(int(e.get("prompt_tokens_before") or 0) for e in events)
    after_prompt = sum(int(e.get("prompt_tokens_after") or 0) for e in events)
    after_comp = sum(int(e.get("completion_tokens") or 0) for e in events)
    # Cache hits store the original completion on the miss; hits record 0.
    # "Before" completions ≈ tokens that would have been billed without cache.
    miss_comp = after_comp
    hit_count = sum(1 for e in events if e.get("cache") == "hit")
    # Approximate before completions: each hit avoided a completion of similar size.
    avg_comp = (miss_comp / max(1, n - hit_count)) if n > hit_count else 0
    before_comp = miss_comp + int(avg_comp * hit_count)

    hits = hit_count
    miss_lat = [float(e.get("latency_ms") or 0) for e in events if e.get("cache") != "hit"]
    all_lat = [float(e.get("latency_ms") or 0) for e in events]
    p50_before = (median(miss_lat) / 1000) if miss_lat else (median(all_lat) / 1000 if all_lat else 0)
    p50_after = (median(all_lat) / 1000) if all_lat else 0
    extract = sum(int(e.get("memory_extract_tokens") or 0) for e in events)
    models = [str(e.get("model") or "") for e in events if e.get("model")]
    model = models[0] if models else ""
    layers: list[str] = []
    for event in events:
        for layer in event.get("layers") or []:
            if layer not in layers:
                layers.append(layer)
    if not layers:
        layers = ["passthrough"]
    credited = [credit_for_layer(name) for name in layers]

    pricing = load_pricing()
    row = lookup_model(model, pricing) if model else None
    before_cost = estimate_cost(model, before_prompt, before_comp, rows=pricing)
    after_cost = estimate_cost(model, after_prompt, after_comp, rows=pricing)

    if before_cost.amount is None or after_cost.amount is None:
        cost_before = before_cost.label
        cost_after = after_cost.label
        cost_delta = ""
    else:
        cost_before = f"${before_cost.amount:.2f}"
        cost_after = f"${after_cost.amount:.2f}"
        cost_delta = _delta(before_cost.amount, after_cost.amount)

    if row:
        pricing_line = f"{row.model} as of {row.last_verified.isoformat()}"
        if before_cost.reason:
            pricing_line += f"  ({before_cost.reason})"
    elif model:
        pricing_line = f"{model} missing from kb/pricing.yaml"
    else:
        pricing_line = "no model recorded"

    hit_rate = f"{(hits / n * 100):.0f}%" if n else "0%"
    extract_line = f"\nmemory_extract_tokens {extract:,}" if extract else ""

    return (
        f"OpenBundle session  (n={n} requests)\n"
        f"                 before     after      delta\n"
        f"prompt tokens    {_num(before_prompt):<10} {_num(after_prompt):<10} {_delta(before_prompt, after_prompt)}\n"
        f"completion tok   {_num(before_comp):<10} {_num(after_comp):<10} {_delta(before_comp, after_comp)}\n"
        f"est. cost        {cost_before:<10} {cost_after:<10} {cost_delta}\n"
        f"p50 latency      {p50_before:.1f}s       {p50_after:.1f}s      {_delta(p50_before, p50_after)}\n"
        f"cache hit rate              {hit_rate}\n"
        f"layers           {', '.join(credited)}"
        f"{extract_line}\n"
        f"advisory         memory not applied ({credit_line('mem0')})\n"
        f"pricing          {pricing_line}"
    )


def print_report(path: Path) -> str:
    text = format_report(load_events(path))
    print(text)
    return text

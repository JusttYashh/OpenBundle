"""Dated per-model pricing. Stale rows never silently become dollars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

STALE_AFTER_DAYS = 30


@dataclass(frozen=True)
class PriceRow:
    model: str
    provider: str
    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float | None
    source: str
    last_verified: date

    @property
    def stale(self) -> bool:
        return date.today() - self.last_verified > timedelta(days=STALE_AFTER_DAYS)

    @property
    def usable(self) -> bool:
        return bool(self.source) and not self.stale


@dataclass(frozen=True)
class CostEstimate:
    amount: float | None
    label: str
    row: PriceRow | None
    reason: str | None = None


def _pricing_path() -> Path:
    return Path(str(resources.files("openbundle") / "kb" / "pricing.yaml"))


def load_pricing(path: Path | None = None) -> dict[str, PriceRow]:
    target = path or _pricing_path()
    with target.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    models = raw.get("models") or {}
    rows: dict[str, PriceRow] = {}
    for name, data in models.items():
        if not isinstance(data, dict):
            continue
        source = str(data.get("source") or "")
        verified_raw = data.get("last_verified")
        if not source or not verified_raw:
            continue
        if isinstance(verified_raw, date):
            verified = verified_raw
        else:
            verified = datetime.strptime(str(verified_raw), "%Y-%m-%d").date()
        rows[name] = PriceRow(
            model=name,
            provider=str(data.get("provider") or ""),
            input_per_mtok=float(data.get("input_per_mtok") or 0),
            output_per_mtok=float(data.get("output_per_mtok") or 0),
            cache_read_per_mtok=(
                float(data["cache_read_per_mtok"])
                if data.get("cache_read_per_mtok") is not None
                else None
            ),
            source=source,
            last_verified=verified,
        )
        aliases = data.get("aliases") or []
        for alias in aliases:
            rows[str(alias)] = rows[name]
    return rows


def lookup_model(model: str, rows: dict[str, PriceRow] | None = None) -> PriceRow | None:
    table = rows if rows is not None else load_pricing()
    if model in table:
        return table[model]
    # strip provider prefixes like anthropic/claude-sonnet-4-6
    if "/" in model:
        stripped = model.split("/", 1)[1]
        if stripped in table:
            return table[stripped]
    return None


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    cache_hit: bool = False,
    rows: dict[str, PriceRow] | None = None,
) -> CostEstimate:
    row = lookup_model(model, rows)
    if row is None:
        return CostEstimate(None, "n/a (pricing unknown)", None, "unknown")
    if not row.source:
        return CostEstimate(None, "n/a (pricing unknown)", row, "unknown")
    if row.stale:
        return CostEstimate(
            None,
            f"n/a (pricing stale|{row.last_verified.isoformat()})",
            row,
            "stale",
        )
    if cache_hit:
        amount = 0.0
    else:
        amount = (prompt_tokens / 1_000_000) * row.input_per_mtok
        amount += (completion_tokens / 1_000_000) * row.output_per_mtok
    return CostEstimate(amount, f"${amount:.2f}", row, None)


def stale_rows(models: list[str] | None = None) -> list[PriceRow]:
    table = load_pricing()
    if models:
        found = [lookup_model(name, table) for name in models]
        return [row for row in found if row and (row.stale or not row.source)]
    return [row for row in dict.fromkeys(table.values()) if row.stale]

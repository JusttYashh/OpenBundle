from datetime import date, timedelta
from pathlib import Path

import yaml

from openbundle.metrics.cost import estimate_cost, load_pricing
from openbundle.metrics.report import format_report


def test_stale_pricing_is_na(tmp_path: Path):
    stale = date.today() - timedelta(days=40)
    path = tmp_path / "pricing.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "models": {
                    "gpt-4.1": {
                        "provider": "openai",
                        "input_per_mtok": 2.0,
                        "output_per_mtok": 8.0,
                        "source": "https://openai.com/api/pricing",
                        "last_verified": stale.isoformat(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    rows = load_pricing(path)
    result = estimate_cost("gpt-4.1", 1000, 100, rows=rows)
    assert result.amount is None
    assert "stale" in result.label


def test_unknown_model_is_na():
    result = estimate_cost("definitely-not-a-model", 10, 10)
    assert result.amount is None
    assert "unknown" in result.label


def test_report_mentions_pricing_date():
    events = [
        {
            "model": "claude-sonnet-4-6",
            "prompt_tokens_before": 100,
            "prompt_tokens_after": 80,
            "completion_tokens": 10,
            "latency_ms": 200,
            "cache": "miss",
            "layers": ["cache"],
        }
    ]
    text = format_report(events)
    assert "pricing" in text
    assert "claude-sonnet-4-6" in text
    assert "OpenBundle exact-hash cache (first-party, MIT)" in text
    assert "layers           cache\n" not in text

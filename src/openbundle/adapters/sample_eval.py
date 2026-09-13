"""Sampled post-response length/format heuristic. Not on the blocking path."""

from __future__ import annotations

from openbundle.config import EvalLayerConfig
from openbundle.pipeline.types import InternalResponse


class SampleEval:
    name = "eval"

    def __init__(self, config: EvalLayerConfig) -> None:
        self.config = config

    def score(self, response: InternalResponse) -> dict[str, str]:
        if not self.config.enabled or not response.ok:
            return {}
        try:
            body = response.body or {}
            text = str(body)
            if len(text) < 2:
                return {"eval": "fail", "eval_reason": "empty response"}
            return {"eval": "pass", "eval_reason": "length/format sanity"}
        except Exception:
            return {}

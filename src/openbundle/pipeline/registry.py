"""Atomic stage registry. Requests snapshot pointers; never see a half-built adapter."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from openbundle.pipeline.jobs import (
    ALL_JOBS,
    DEGRADED,
    LIVE,
    OFF,
    WARMING,
    ADVISORY,
)


@dataclass
class StageInfo:
    job_id: str
    tool_id: str
    state: str = OFF
    last_error: str = ""
    reason: str = ""
    fail_open_count: int = 0
    hard_down: bool = False


class StageRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stages: dict[str, Any] = {}
        self._info: dict[str, StageInfo] = {
            job.id: StageInfo(job_id=job.id, tool_id=job.tool_id) for job in ALL_JOBS
        }
        self.fail_open_count = 0
        self.nemo_rail_tokens = 0
        self.nemo_rail_ms = 0.0
        self.local_obs = False
        self.hosted_obs_disclosure = True

    def snapshot(self) -> dict[str, Any]:
        """Copy of stage pointers. Safe for the rest of a request."""
        with self._lock:
            return dict(self._stages)

    def info_snapshot(self) -> dict[str, StageInfo]:
        with self._lock:
            return {key: StageInfo(**vars(val)) for key, val in self._info.items()}

    def get_info(self, job_id: str) -> StageInfo:
        with self._lock:
            info = self._info[job_id]
            return StageInfo(**vars(info))

    def publish(
        self,
        job_id: str,
        stage: Any,
        state: str = LIVE,
        *,
        tool_id: str | None = None,
    ) -> None:
        """Atomic pointer swap. `stage` must already be fully constructed.

        LIVE is refused without a stage object — status cannot claim live for a missing adapter.
        """
        if state == LIVE and stage is None:
            self.set_state(job_id, OFF, reason="refused live publish without a constructed stage")
            return
        with self._lock:
            stages = dict(self._stages)
            if stage is None:
                stages.pop(job_id, None)
            else:
                stages[job_id] = stage
            self._stages = stages
            info = self._info[job_id]
            if tool_id:
                info.tool_id = tool_id
            info.state = state
            if state == LIVE:
                info.hard_down = False
                info.reason = ""
            elif stage is None and state == OFF:
                pass

    def constructed(self, job_id: str) -> Any | None:
        with self._lock:
            return self._stages.get(job_id)

    def is_constructed_live(self, job_id: str) -> bool:
        with self._lock:
            info = self._info.get(job_id)
            return bool(info and info.state == LIVE and job_id in self._stages)

    def lynx_constructed(self) -> bool:
        """True only when a Lynx adapter object is in the snapshot — never a flag."""
        with self._lock:
            info = self._info.get("rag_faithfulness")
            if not (info and info.state == LIVE and "rag_faithfulness" in self._stages):
                return False
            return getattr(self._stages["rag_faithfulness"], "kind", None) == "lynx"

    def live_jobs(self) -> list[str]:
        with self._lock:
            return [
                job_id
                for job_id, info in self._info.items()
                if info.state == LIVE and job_id in self._stages
            ]

    def set_state(
        self,
        job_id: str,
        state: str,
        *,
        reason: str = "",
        last_error: str = "",
        hard_down: bool = False,
        stage: Any | None = None,
        replace_stage: bool = False,
    ) -> None:
        with self._lock:
            info = self._info[job_id]
            if replace_stage:
                stages = dict(self._stages)
                if stage is None:
                    stages.pop(job_id, None)
                else:
                    stages[job_id] = stage
                self._stages = stages
            if state == LIVE and job_id not in self._stages:
                info.state = OFF
                info.reason = reason or "refused live without a constructed stage"
                if last_error:
                    info.last_error = last_error
                info.hard_down = hard_down
                return
            info.state = state
            if reason:
                info.reason = reason
            if last_error:
                info.last_error = last_error
            info.hard_down = hard_down

    def fail_open(self, job_id: str, error: BaseException | str) -> None:
        text = str(error) or error.__class__.__name__
        with self._lock:
            info = self._info[job_id]
            if info.hard_down:
                return
            info.state = DEGRADED
            info.last_error = text
            info.fail_open_count += 1
            self.fail_open_count += 1

    def recover(self, job_id: str) -> None:
        with self._lock:
            info = self._info[job_id]
            if info.hard_down:
                return
            if info.state == DEGRADED and job_id in self._stages:
                info.state = LIVE

    def mark_advisory(self, job_id: str, tool_id: str, reason: str) -> None:
        with self._lock:
            if job_id not in self._info:
                self._info[job_id] = StageInfo(job_id=job_id, tool_id=tool_id)
            info = self._info[job_id]
            info.tool_id = tool_id
            info.state = ADVISORY
            info.reason = reason

    def degraded_jobs(self) -> list[tuple[str, str]]:
        with self._lock:
            return [
                (job_id, info.last_error or info.reason)
                for job_id, info in self._info.items()
                if info.state == DEGRADED
            ]

    def warming_jobs(self) -> list[str]:
        with self._lock:
            return [job_id for job_id, info in self._info.items() if info.state == WARMING]

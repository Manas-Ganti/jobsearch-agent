"""Stage protocol + the reduce-based runner.

The orchestrator has no control flow of its own: it folds `list[JobPosting]`
through an ordered list of stages. Reordering a feature is a config edit.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from functools import reduce
from typing import Protocol, runtime_checkable

from .models import JobPosting

log = logging.getLogger(__name__)


@runtime_checkable
class Stage(Protocol):
    """Every pipeline stage. No other signature is allowed."""

    name: str

    def run(self, jobs: list[JobPosting]) -> list[JobPosting]: ...


@dataclass
class StageResult:
    name: str
    count_in: int
    count_out: int
    seconds: float
    error: str | None = None


@dataclass
class Pipeline:
    stages: list[Stage]
    continue_on_error: bool = True
    results: list[StageResult] = field(default_factory=list)

    def run(self, jobs: list[JobPosting] | None = None) -> list[JobPosting]:
        self.results = []
        return reduce(self._step, self.stages, list(jobs or []))

    def _step(self, jobs: list[JobPosting], stage: Stage) -> list[JobPosting]:
        started = time.perf_counter()
        name = getattr(stage, "name", type(stage).__name__)
        try:
            out = stage.run(jobs)
        except Exception as exc:  # a broken enricher must not lose the whole run
            elapsed = time.perf_counter() - started
            self.results.append(StageResult(name, len(jobs), len(jobs), elapsed, repr(exc)))
            log.exception("stage %s failed", name)
            if not self.continue_on_error:
                raise
            return jobs
        elapsed = time.perf_counter() - started
        self.results.append(StageResult(name, len(jobs), len(out), elapsed))
        log.info("%-18s %4d → %4d  (%.2fs)", name, len(jobs), len(out), elapsed)
        return out

    def summary(self) -> str:
        lines = [f"{'stage':<18}{'in':>6}{'out':>6}{'sec':>8}"]
        for r in self.results:
            flag = "  ERROR" if r.error else ""
            lines.append(f"{r.name:<18}{r.count_in:>6}{r.count_out:>6}{r.seconds:>8.2f}{flag}")
        return "\n".join(lines)

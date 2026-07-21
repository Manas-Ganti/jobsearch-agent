"""The Fetch stage: config `sources:` → registry → `list[JobPosting]`.

This is the only place that knows sources exist, and it still only knows them
by name — the orchestrator never imports a concrete source.
"""

from __future__ import annotations

import logging

from ..enrichers import Enricher, register_enricher
from ..models import JobPosting
from . import SOURCE_REGISTRY

log = logging.getLogger(__name__)


@register_enricher("fetch")
class FetchStage(Enricher):
    def configure(self, only: list[str] | None = None, limit_per_source: int = 0) -> None:
        self.only = set(only or [])
        self.limit_per_source = limit_per_source
        SOURCE_REGISTRY.discover(__package__)

    def run(self, jobs: list[JobPosting]) -> list[JobPosting]:
        seen = {job.id for job in jobs}
        out = list(jobs)
        for source_cfg in self.ctx.config.sources:
            label = source_cfg.name or source_cfg.type
            if self.only and label not in self.only:
                continue
            try:
                source = SOURCE_REGISTRY.create(
                    source_cfg.type, self.ctx, **source_cfg.build_params()
                )
                source.name = label  # instance label, so `source` reads e.g. "anthropic"
                raws = source.fetch()
            except Exception as exc:  # one dead board must not sink the run
                log.error("source %s (%s) failed: %s", label, source_cfg.type, exc)
                continue
            if self.limit_per_source:
                raws = raws[: self.limit_per_source]
            for raw in raws:
                if not raw.url:
                    continue
                job = raw.to_job()
                if job.id in seen:
                    continue
                seen.add(job.id)
                out.append(job)
        return out

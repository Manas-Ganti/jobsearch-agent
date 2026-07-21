"""Enricher registry + the base class most stages inherit.

A new feature is: one file in this folder, one `@register_enricher` decorator,
one line in `config.yaml`'s `pipeline:` list. Nothing else changes.
"""

from __future__ import annotations

from ..context import Context
from ..models import JobPosting
from ..registry import Registry

ENRICHER_REGISTRY: Registry["Enricher"] = Registry("enricher")
register_enricher = ENRICHER_REGISTRY.register


class Enricher:
    """Default stage shape: map/filter over one job at a time.

    Override `process` for per-job work (return None to drop the job), or
    override `run` when the stage needs to see the whole list (ranking, dedup,
    delivery). Either way the signature the pipeline sees is unchanged.
    """

    name: str = "enricher"

    def __init__(self, ctx: Context, **params: object) -> None:
        self.ctx = ctx
        self.configure(**params)  # unknown config keys raise here, loudly

    def configure(self) -> None:
        """Override to accept config params as keyword arguments."""

    def run(self, jobs: list[JobPosting]) -> list[JobPosting]:
        out: list[JobPosting] = []
        for job in jobs:
            result = self.process(job)
            if result is not None:
                out.append(result)
        return out

    def process(self, job: JobPosting) -> JobPosting | None:
        return job


__all__ = ["ENRICHER_REGISTRY", "Enricher", "register_enricher"]

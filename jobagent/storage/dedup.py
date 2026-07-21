"""Dedup: hash every posting, record the sighting, keep only what's new.

This is what turns a daily crawl into a daily *digest* — the DB write is a side
effect, but the data still flows through the standard signature.
"""

from __future__ import annotations

import hashlib
import logging

from ..enrichers import Enricher, register_enricher
from ..models import TAG_NEW, JobPosting

log = logging.getLogger(__name__)


def fingerprint(job: JobPosting) -> str:
    """Changes when the posting's substance changes, not when tracking params do."""
    body = "|".join([job.title, job.location, job.description]).strip().lower()
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]


@register_enricher("dedup")
class DedupStage(Enricher):
    def configure(self, only_new: bool = True, include_changed: bool = True) -> None:
        self.only_new = only_new
        self.include_changed = include_changed

    def run(self, jobs: list[JobPosting]) -> list[JobPosting]:
        out: list[JobPosting] = []
        for job in jobs:
            is_new, changed = self.ctx.db.upsert(job, fingerprint(job))
            job.metadata["first_seen"] = self.ctx.db.first_seen(job.id)
            if is_new:
                job.tag(TAG_NEW)
            elif changed:
                job.tag("changed")

            if not self.only_new or is_new or (changed and self.include_changed):
                out.append(job)
        log.info("dedup: %d seen → %d new/changed", len(jobs), len(out))
        return out

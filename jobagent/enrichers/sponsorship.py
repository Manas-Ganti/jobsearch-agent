"""Sponsorship: tag postings that rule out visa sponsorship.

The user is on an F-1, so this is load-bearing. It runs *before* the expensive
stages so disqualifying postings never reach the ranker or the LLM. Pure regex —
no model call. Ambiguity is resolved toward keeping the posting.
"""

from __future__ import annotations

import logging
import re

from ..models import TAG_NO_SPONSORSHIP, JobPosting
from . import Enricher, register_enricher

log = logging.getLogger(__name__)

# Explicit refusals to sponsor.
NO_SPONSORSHIP = [
    r"\b(?:will|can)\s*not\s+(?:be\s+able\s+to\s+)?(?:provide|offer|sponsor)\b[^.]{0,40}\bsponsor",
    r"\bno\s+(?:visa\s+)?sponsorship\b",
    r"\bunable\s+to\s+sponsor\b",
    r"\bdoes\s+not\s+(?:provide|offer)\s+(?:visa\s+)?sponsorship\b",
    r"\bsponsorship\s+is\s+not\s+(?:available|offered|provided)\b",
    r"\bnot\s+(?:currently\s+)?(?:sponsoring|considering)\b[^.]{0,30}\bvisa",
    r"\bwithout\s+(?:the\s+need\s+for\s+)?(?:current\s+or\s+future\s+)?sponsorship\b",
]

# Citizenship / clearance requirements that also exclude an F-1 candidate.
CITIZENSHIP = [
    r"\bU\.?S\.?\s+citizen(?:ship)?\s+(?:is\s+)?(?:required|only)\b",
    r"\bmust\s+be\s+a\s+U\.?S\.?\s+citizen\b",
    r"\b(?:active\s+)?(?:security|ts/sci|top\s+secret)\s+clearance\b",
    r"\bITAR\b",
    r"\bgreen\s+card\s+holder[s]?\s+only\b",
]

# Positive signals — a posting that says it *does* sponsor.
SPONSORS = [
    r"\bwe\s+(?:do\s+)?sponsor\b",
    r"\bsponsorship\s+(?:is\s+)?available\b",
    r"\bwilling\s+to\s+sponsor\b",
    r"\bvisa\s+sponsorship\s+(?:is\s+)?(?:offered|provided|supported)\b",
    r"\bh-?1b\s+(?:transfer|sponsorship)\s+(?:available|offered|supported)\b",
]


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.I) for p in patterns]


@register_enricher("sponsorship")
class SponsorshipEnricher(Enricher):
    def configure(
        self,
        drop_no_sponsorship: bool = True,
        drop_citizenship_required: bool = True,
        extra_no_sponsorship: list[str] | None = None,
    ) -> None:
        self.drop_no_sponsorship = drop_no_sponsorship
        self.drop_citizenship_required = drop_citizenship_required
        self.no_sponsorship = _compile(NO_SPONSORSHIP + (extra_no_sponsorship or []))
        self.citizenship = _compile(CITIZENSHIP)
        self.sponsors = _compile(SPONSORS)

    def process(self, job: JobPosting) -> JobPosting | None:
        text = f"{job.title}\n{job.description}"

        # Refusals are checked first on purpose: "no visa sponsorship is
        # available" contains the positive phrase "sponsorship is available".
        if hit := _first(self.no_sponsorship, text):
            job.tag(TAG_NO_SPONSORSHIP)
            job.metadata["sponsorship"] = {"status": "none", "evidence": hit}
            if self.drop_no_sponsorship:
                log.info("drop %s — states no sponsorship", job.url)
                return None
            return job

        if hit := _first(self.sponsors, text):
            job.tag("sponsorship-available")
            job.metadata["sponsorship"] = {"status": "available", "evidence": hit}
            return job

        if hit := _first(self.citizenship, text):
            job.tag("citizenship-required")
            job.metadata["sponsorship"] = {"status": "citizenship", "evidence": hit}
            if self.drop_citizenship_required:
                log.info("drop %s — citizenship/clearance required", job.url)
                return None
        return job


def _first(patterns: list[re.Pattern], text: str) -> str | None:
    """Return the matched snippet, so a wrong drop is debuggable from metadata."""
    for pat in patterns:
        if m := pat.search(text):
            return m.group(0).strip()
    return None

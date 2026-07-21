"""KeywordFilter: cheap title/location prefilter. No model, runs first.

Everything it discards is a posting we never pay to embed or score.
"""

from __future__ import annotations

import logging
import re

from ..models import JobPosting
from . import Enricher, register_enricher

log = logging.getLogger(__name__)


def _compile(patterns: list[str]) -> list[re.Pattern]:
    """Literal keywords, word-bounded where that makes sense ("c++" must still
    match). Prefix a pattern with `re:` to pass a raw regex instead."""
    compiled = []
    for p in patterns:
        if p.startswith("re:"):
            compiled.append(re.compile(p[3:], re.I))
            continue
        left = r"\b" if p[:1].isalnum() else ""
        right = r"\b" if p[-1:].isalnum() else ""
        compiled.append(re.compile(f"{left}{re.escape(p)}{right}", re.I))
    return compiled


def _any(patterns: list[re.Pattern], text: str) -> str | None:
    for pat in patterns:
        if pat.search(text):
            return pat.pattern
    return None


@register_enricher("keyword_filter")
class KeywordFilter(Enricher):
    def configure(
        self,
        include_title: list[str] | None = None,
        exclude_title: list[str] | None = None,
        exclude_description: list[str] | None = None,
        locations: list[str] | None = None,
        allow_remote: bool = True,
    ) -> None:
        self.include_title = _compile(include_title or [])
        self.exclude_title = _compile(exclude_title or [])
        self.exclude_description = _compile(exclude_description or [])
        self.locations = _compile(locations or [])
        self.allow_remote = allow_remote

    def process(self, job: JobPosting) -> JobPosting | None:
        title = job.title or ""
        if self.include_title and not _any(self.include_title, title):
            return None
        if (hit := _any(self.exclude_title, title)) is not None:
            log.debug("drop %s — title matches %s", job.url, hit)
            return None
        if (hit := _any(self.exclude_description, job.description)) is not None:
            log.debug("drop %s — description matches %s", job.url, hit)
            return None

        location = job.location or ""
        is_remote = bool(re.search(r"\bremote\b", f"{location} {title}", re.I))
        if is_remote:
            job.tag("remote")
        if self.locations and not _any(self.locations, location):
            if not (self.allow_remote and is_remote):
                return None
        return job

"""The shared data contracts.

`JobPosting` is the only shape that flows through the pipeline. `RawPosting` is
the source-level shape: it exists solely so a `Source` can hand back something
that may not be structured yet. Everything downstream of Fetch sees `JobPosting`.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field

# Tags with meaning across stages. Feature-specific tags are free-form strings.
TAG_NEEDS_EXTRACTION = "needs-extraction"
TAG_NO_SPONSORSHIP = "no-sponsorship"
TAG_NEW = "new"

_TRACKING_PARAMS = re.compile(r"^(utm_|gh_src$|lever-source|source$|ref$|src$)", re.I)


def canonical_url(url: str) -> str:
    """Strip tracking params and normalise so the same posting hashes the same."""
    parts = urlsplit(url.strip())
    query = "&".join(
        q
        for q in parts.query.split("&")
        if q and not _TRACKING_PARAMS.match(q.split("=", 1)[0])
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def canonical_id(
    url: str | None, company: str = "", title: str = "", location: str = ""
) -> str:
    """Stable id: canonical URL when we have one, else (company, title, location)."""
    if url:
        key = canonical_url(url)
    else:
        key = "|".join(p.strip().lower() for p in (company, title, location))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


class JobPosting(BaseModel):
    """The one job shape. New features attach to `tags` / `metadata`."""

    id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    posted_date: date | None = None
    source: str

    # enrichment — all optional, filled by later stages
    score: float | None = None
    rationale: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    def tag(self, *names: str) -> "JobPosting":
        for name in names:
            if name not in self.tags:
                self.tags.append(name)
        return self

    def untag(self, *names: str) -> "JobPosting":
        self.tags = [t for t in self.tags if t not in names]
        return self

    def has(self, name: str) -> bool:
        return name in self.tags

    def searchable_text(self) -> str:
        """What the ranker/scorer embeds. Kept in one place so both agree."""
        return f"{self.title}\n{self.company} — {self.location}\n\n{self.description}"


class RawPosting(BaseModel):
    """What a `Source` yields.

    API sources fill `title`/`description` and map straight through. Browser
    sources fill `raw` only; the Extract stage turns that into real fields.
    """

    source: str
    company: str
    url: str
    title: str | None = None
    location: str | None = None
    description: str | None = None
    posted_date: date | None = None
    raw: str | None = None
    metadata: dict = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def needs_extraction(self) -> bool:
        return not (self.title and self.description)

    def to_job(self) -> JobPosting:
        job = JobPosting(
            id=canonical_id(self.url, self.company, self.title or "", self.location or ""),
            title=self.title or "",
            company=self.company,
            location=self.location or "",
            url=self.url,
            description=self.description or "",
            posted_date=self.posted_date,
            source=self.source,
            metadata=dict(self.metadata),
        )
        if self.needs_extraction:
            # Park the unstructured payload where Extract can find it.
            job.metadata["raw"] = self.raw or ""
            job.tag(TAG_NEEDS_EXTRACTION)
        return job

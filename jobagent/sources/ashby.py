"""Ashby job boards — public posting API, no key needed."""

from __future__ import annotations

import logging
from datetime import datetime

from ..models import RawPosting
from ..textutil import html_to_text
from . import BaseSource, register_source

log = logging.getLogger(__name__)

API = "https://api.ashbyhq.com/posting-api/job-board/{board}"


@register_source("ashby")
class AshbySource(BaseSource):
    def configure(
        self, board: str = "", company: str | None = None, include_compensation: bool = True
    ) -> None:
        if not board:
            raise ValueError("ashby source needs a `board` (the job board name)")
        self.board = board
        self.company = company or board.replace("-", " ").title()
        self.include_compensation = include_compensation

    def fetch(self) -> list[RawPosting]:
        data = self.http.get_json(
            API.format(board=self.board),
            params={"includeCompensation": str(self.include_compensation).lower()},
        )
        postings: list[RawPosting] = []
        for job in data.get("jobs", []):
            if job.get("isListed") is False:
                continue
            description = job.get("descriptionPlain") or html_to_text(
                job.get("descriptionHtml", "")
            )
            postings.append(
                RawPosting(
                    source=self.name,
                    company=self.company,
                    url=job.get("jobUrl") or job.get("applyUrl", ""),
                    title=job.get("title"),
                    location=job.get("location") or "",
                    description=description,
                    posted_date=_date(job.get("publishedAt")),
                    metadata={
                        "board": self.board,
                        "team": job.get("team"),
                        "employment_type": job.get("employmentType"),
                        "is_remote": job.get("isRemote"),
                        "compensation": job.get("compensation"),
                    },
                )
            )
        log.info("ashby:%s → %d postings", self.board, len(postings))
        return postings


def _date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None

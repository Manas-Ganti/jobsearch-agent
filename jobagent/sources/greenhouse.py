"""Greenhouse job boards — public JSON API, no key needed."""

from __future__ import annotations

import logging
from datetime import datetime

from ..models import RawPosting
from ..textutil import html_to_text
from . import BaseSource, register_source

log = logging.getLogger(__name__)

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


@register_source("greenhouse")
class GreenhouseSource(BaseSource):
    def configure(self, board: str = "", company: str | None = None) -> None:
        if not board:
            raise ValueError("greenhouse source needs a `board` (the board token)")
        self.board = board
        self.company = company or board.replace("-", " ").title()

    def fetch(self) -> list[RawPosting]:
        data = self.http.get_json(API.format(board=self.board), params={"content": "true"})
        postings: list[RawPosting] = []
        for job in data.get("jobs", []):
            postings.append(
                RawPosting(
                    source=self.name,
                    company=self.company,
                    url=job.get("absolute_url", ""),
                    title=job.get("title"),
                    location=(job.get("location") or {}).get("name", ""),
                    description=html_to_text(job.get("content", "")),
                    posted_date=_date(job.get("first_published") or job.get("updated_at")),
                    metadata={"board": self.board, "greenhouse_id": job.get("id")},
                )
            )
        log.info("greenhouse:%s → %d postings", self.board, len(postings))
        return postings


def _date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None

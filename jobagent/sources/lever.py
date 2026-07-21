"""Lever job boards — public JSON API, no key needed."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..models import RawPosting
from ..textutil import html_to_text
from . import BaseSource, register_source

log = logging.getLogger(__name__)

API = "https://api.lever.co/v0/postings/{account}"


@register_source("lever")
class LeverSource(BaseSource):
    def configure(self, account: str = "", company: str | None = None) -> None:
        if not account:
            raise ValueError("lever source needs an `account` (the lever.co slug)")
        self.account = account
        self.company = company or account.replace("-", " ").title()

    def fetch(self) -> list[RawPosting]:
        data = self.http.get_json(API.format(account=self.account), params={"mode": "json"})
        postings: list[RawPosting] = []
        for job in data:
            categories = job.get("categories") or {}
            body = job.get("descriptionPlain") or html_to_text(job.get("description", ""))
            extras = "\n\n".join(
                f"{sec.get('text', '')}\n{html_to_text(sec.get('content', ''))}"
                for sec in job.get("lists", [])
            )
            postings.append(
                RawPosting(
                    source=self.name,
                    company=self.company,
                    url=job.get("hostedUrl", ""),
                    title=job.get("text"),
                    location=categories.get("location", ""),
                    description=f"{body}\n\n{extras}".strip(),
                    posted_date=_date(job.get("createdAt")),
                    metadata={
                        "account": self.account,
                        "team": categories.get("team"),
                        "commitment": categories.get("commitment"),
                    },
                )
            )
        log.info("lever:%s → %d postings", self.account, len(postings))
        return postings


def _date(ms: int | None):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()

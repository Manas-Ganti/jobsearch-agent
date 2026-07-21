"""Extract: LLM turns unstructured page text into real `JobPosting` fields.

Only touches jobs tagged `needs-extraction` (browser sources). API sources map
directly and pass through untouched, so this stage costs nothing when unused.
"""

from __future__ import annotations

import logging
from datetime import date

from pydantic import BaseModel, Field

from ..backends import complete_model
from ..models import TAG_NEEDS_EXTRACTION, JobPosting
from ..textutil import truncate
from . import Enricher, register_enricher

log = logging.getLogger(__name__)

SYSTEM = (
    "You extract job postings from raw web page text. Report only what the page "
    "says. If a field is absent, use an empty string."
)

PROMPT = """Extract the job posting from this page.

Company (already known): {company}
URL: {url}

--- PAGE TEXT ---
{text}
--- END PAGE TEXT ---

Return the job title, the location as written, the posting date as YYYY-MM-DD if
stated, and the description (responsibilities + requirements, plain text).
Set is_job_posting to false if this page is not a single job posting."""


class Extracted(BaseModel):
    is_job_posting: bool = True
    title: str = ""
    location: str = ""
    posted_date: str = ""
    description: str = ""
    employment_type: str = Field(default="", description="full-time, intern, contract…")


@register_enricher("extract")
class ExtractStage(Enricher):
    def configure(self, max_input_chars: int = 12000, max_description_chars: int = 8000) -> None:
        self.max_input_chars = max_input_chars
        self.max_description_chars = max_description_chars

    def process(self, job: JobPosting) -> JobPosting | None:
        if not job.has(TAG_NEEDS_EXTRACTION):
            return job

        raw = job.metadata.pop("raw", "") or job.description
        if not raw.strip():
            return None

        result = complete_model(
            self.ctx.llm,
            PROMPT.format(
                company=job.company,
                url=job.url,
                text=truncate(raw, self.max_input_chars),
            ),
            Extracted,
            system=SYSTEM,
        )
        if result is None or not result.is_job_posting or not result.title:
            log.info("extract dropped %s", job.url)
            return None

        job.title = result.title
        job.location = result.location
        job.description = truncate(
            result.description or raw, self.max_description_chars
        )
        job.posted_date = _parse_date(result.posted_date)
        if result.employment_type:
            job.metadata["employment_type"] = result.employment_type
        return job.untag(TAG_NEEDS_EXTRACTION)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip()[:10]) if value.strip() else None
    except ValueError:
        return None

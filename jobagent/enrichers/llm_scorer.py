"""LLMScorer: the only stage that sends postings to the LLM one by one.

It scores at most `top_n` postings — whatever the embedding ranker put on top.
Sending everything here would defeat the cost model.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ..backends import complete_model
from ..models import JobPosting
from ..textutil import truncate
from . import Enricher, register_enricher

log = logging.getLogger(__name__)

SYSTEM = (
    "You are a hiring-match assessor for one specific candidate. You are strict: "
    "a high score means the candidate would plausibly get an interview."
)

PROMPT = """CANDIDATE PROFILE
{profile}

JOB POSTING
Title: {title}
Company: {company}
Location: {location}

{description}

Score how good a match this job is for this candidate, 0.0 to 1.0:
  0.8-1.0 strong match — core skills and level line up
  0.5-0.8 plausible — adjacent domain or slight level mismatch
  0.0-0.5 weak — different field, wrong level, or disqualifying requirement
Weigh domain overlap, required experience level, and any hard requirements the
candidate cannot meet. Give a one-sentence rationale naming the deciding factor.
"""


class Assessment(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    rationale: str
    concerns: list[str] = Field(default_factory=list)


@register_enricher("llm_scorer")
class LLMScorer(Enricher):
    def configure(
        self,
        top_n: int = 15,
        min_score: float = 0.0,
        keep_unscored_tail: bool = False,
        max_profile_chars: int = 6000,
        max_description_chars: int = 6000,
    ) -> None:
        self.top_n = top_n
        self.min_score = min_score
        self.keep_unscored_tail = keep_unscored_tail
        self.max_profile_chars = max_profile_chars
        self.max_description_chars = max_description_chars

    def run(self, jobs: list[JobPosting]) -> list[JobPosting]:
        if not jobs:
            return jobs
        profile = truncate(self.ctx.profile.text.strip(), self.max_profile_chars)
        if not profile:
            log.warning("no resume/portfolio text — skipping LLM scoring")
            return jobs

        candidates, tail = jobs[: self.top_n], jobs[self.top_n :]
        scored = [self._score(job, profile) for job in candidates]
        # An LLM failure leaves score None — keep those rather than silently
        # dropping a posting we simply failed to assess.
        scored = [j for j in scored if j.score is None or j.score >= self.min_score]

        out = scored + tail if self.keep_unscored_tail else scored
        return sorted(out, key=lambda j: (j.score is not None, j.score or 0.0), reverse=True)

    def _score(self, job: JobPosting, profile: str) -> JobPosting:
        result = complete_model(
            self.ctx.llm,
            PROMPT.format(
                profile=profile,
                title=job.title,
                company=job.company,
                location=job.location,
                description=truncate(job.description, self.max_description_chars),
            ),
            Assessment,
            system=SYSTEM,
        )
        if result is None:
            log.warning("scoring failed for %s — leaving unscored", job.url)
            return job
        job.score = round(max(0.0, min(1.0, result.score)), 3)
        job.rationale = result.rationale.strip()
        if result.concerns:
            job.metadata["concerns"] = result.concerns
        return job

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
    "a high rating means the candidate would plausibly get an interview."
)

PROMPT = """CANDIDATE PROFILE
{profile}

JOB POSTING
Title: {title}
Company: {company}
Location: {location}

{description}

Rate this posting for THIS candidate. Judge each axis separately.

domain_fit (0-10): how close the technical domain is to what the candidate has
  actually done. 10 = same subfield and tools; 5 = adjacent (general ML vs. RL);
  0 = unrelated field.
level_fit (0-10): 10 = the candidate's experience level is what the posting asks
  for; 5 = one level off; 0 = far off in either direction (new grad vs. 10+ years
  required, or a senior IC role vs. an internship).
blockers: every hard requirement in the posting this candidate cannot meet —
  years of experience, required degree, citizenship or clearance, on-site in a
  country they are not in, a licence they lack. Empty list if there are none.
rationale: ONE sentence naming the single deciding factor.

Be discriminating. Most postings are not a 10, and near-identical roles should
still separate on the details.
"""


class Assessment(BaseModel):
    """Three narrow judgements a 7B model can make well, instead of one holistic
    float it cannot. The final 0-1 score is computed from these in Python."""

    domain_fit: float = Field(ge=0.0, le=10.0)
    level_fit: float = Field(ge=0.0, le=10.0)
    blockers: list[str] = Field(default_factory=list)
    rationale: str


@register_enricher("llm_scorer")
class LLMScorer(Enricher):
    def configure(
        self,
        top_n: int = 15,
        min_score: float = 0.0,
        keep_unscored_tail: bool = False,
        domain_weight: float = 0.65,
        blocker_penalty: float = 0.25,
        max_profile_chars: int = 6000,
        max_description_chars: int = 6000,
    ) -> None:
        self.top_n = top_n
        self.min_score = min_score
        self.keep_unscored_tail = keep_unscored_tail
        self.domain_weight = domain_weight
        self.blocker_penalty = blocker_penalty
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

        job.score = self._combine(result)
        job.rationale = result.rationale.strip()
        job.metadata["fit"] = {
            "domain": result.domain_fit,
            "level": result.level_fit,
        }
        if result.blockers:
            job.metadata["blockers"] = result.blockers
            job.tag("has-blockers")
        return job

    def _combine(self, result: Assessment) -> float:
        """Weighted sub-scores, discounted once per hard blocker. Doing this in
        Python rather than asking for one number is what gives the small model
        room to separate otherwise-identical roles."""
        base = (
            self.domain_weight * result.domain_fit
            + (1.0 - self.domain_weight) * result.level_fit
        ) / 10.0
        base *= max(0.0, 1.0 - self.blocker_penalty * len(result.blockers))
        return round(max(0.0, min(1.0, base)), 3)

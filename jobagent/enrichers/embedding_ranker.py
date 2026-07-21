"""EmbeddingRanker: cheap first-pass ranking by cosine(resume, posting).

This is what makes the cost model work — the LLM only ever sees what survives
here. Similarity lands in `metadata["similarity"]`, not in `score`, which stays
reserved for the LLM's judgement.
"""

from __future__ import annotations

import logging

from ..backends import cosine
from ..models import JobPosting
from ..textutil import truncate
from . import Enricher, register_enricher

log = logging.getLogger(__name__)


@register_enricher("embedding_ranker")
class EmbeddingRanker(Enricher):
    def configure(
        self,
        top_k: int = 40,
        min_similarity: float = 0.0,
        max_chars: int = 4000,
    ) -> None:
        self.top_k = top_k
        self.min_similarity = min_similarity
        self.max_chars = max_chars

    def run(self, jobs: list[JobPosting]) -> list[JobPosting]:
        if not jobs:
            return jobs
        profile = self.ctx.profile.text.strip()
        if not profile:
            log.warning("no resume/portfolio text — skipping embedding ranking")
            return jobs

        texts = [truncate(job.searchable_text(), self.max_chars) for job in jobs]
        vectors = self.ctx.embeddings.embed([truncate(profile, self.max_chars), *texts])
        resume_vec, job_vecs = vectors[0], vectors[1:]

        for job, vec in zip(jobs, job_vecs):
            job.metadata["similarity"] = round(cosine(resume_vec, vec), 4)

        ranked = sorted(jobs, key=lambda j: j.metadata["similarity"], reverse=True)
        kept = [j for j in ranked if j.metadata["similarity"] >= self.min_similarity]
        return kept[: self.top_k] if self.top_k else kept

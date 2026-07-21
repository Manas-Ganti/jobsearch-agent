from __future__ import annotations

from conftest import make_job

from jobagent.enrichers.embedding_ranker import EmbeddingRanker
from jobagent.enrichers.extract import ExtractStage
from jobagent.enrichers.keyword_filter import KeywordFilter
from jobagent.enrichers.llm_scorer import LLMScorer
from jobagent.enrichers.salary import SalaryEnricher
from jobagent.enrichers.sponsorship import SponsorshipEnricher
from jobagent.models import TAG_NEEDS_EXTRACTION, TAG_NO_SPONSORSHIP


# --- keyword filter ---------------------------------------------------------
def test_keyword_filter_keeps_matches_and_drops_the_rest(ctx):
    stage = KeywordFilter(ctx, include_title=["machine learning", "research engineer"],
                          exclude_title=["director"])
    jobs = [
        make_job(title="Research Engineer, RL"),
        make_job(title="Director of Machine Learning", url="https://x.example/2"),
        make_job(title="Enterprise Sales Lead", url="https://x.example/3"),
    ]
    assert [j.title for j in stage.run(jobs)] == ["Research Engineer, RL"]


def test_keyword_filter_allows_remote_outside_listed_locations(ctx):
    stage = KeywordFilter(ctx, locations=["new york"], allow_remote=True)
    job = make_job(location="Remote (US)")
    assert stage.run([job]) == [job]
    assert job.has("remote")


def test_keyword_filter_handles_punctuation_keywords(ctx):
    stage = KeywordFilter(ctx, include_title=["c++"])
    assert len(stage.run([make_job(title="C++ Perception Engineer")])) == 1


# --- sponsorship ------------------------------------------------------------
def test_sponsorship_drops_explicit_refusals(ctx):
    stage = SponsorshipEnricher(ctx)
    job = make_job(description="We are unable to sponsor visas for this role.")
    assert stage.run([job]) == []


def test_sponsorship_can_tag_without_dropping(ctx):
    stage = SponsorshipEnricher(ctx, drop_no_sponsorship=False)
    job = make_job(description="No visa sponsorship is available for this position.")
    assert stage.run([job]) == [job]
    assert job.has(TAG_NO_SPONSORSHIP)
    assert job.metadata["sponsorship"]["evidence"]


def test_sponsorship_positive_signal_wins(ctx):
    stage = SponsorshipEnricher(ctx)
    job = make_job(description="Visa sponsorship is offered for exceptional candidates.")
    assert stage.run([job]) == [job]
    assert job.has("sponsorship-available")


def test_sponsorship_drops_clearance_requirements(ctx):
    stage = SponsorshipEnricher(ctx)
    job = make_job(description="Must hold an active TS/SCI clearance.")
    assert stage.run([job]) == []


def test_sponsorship_leaves_silent_postings_alone(ctx):
    stage = SponsorshipEnricher(ctx)
    job = make_job(description="Build RL agents. Great team, great benefits.")
    assert stage.run([job]) == [job]
    assert not job.tags


# --- ranking / scoring ------------------------------------------------------
def test_ranker_orders_by_similarity_and_truncates(ctx):
    stage = EmbeddingRanker(ctx, top_k=2)
    jobs = [
        make_job(description="Payroll administration and benefits", url="https://x.example/a"),
        make_job(description="reinforcement learning computer vision", url="https://x.example/b"),
        make_job(description="reinforcement learning engineer", url="https://x.example/c"),
    ]
    out = stage.run(jobs)
    assert len(out) == 2
    assert "payroll" not in out[0].description.lower()
    assert out[0].metadata["similarity"] >= out[1].metadata["similarity"]


def test_scorer_only_touches_top_n(ctx, llm):
    llm.responses = [{"score": 0.9, "rationale": "RL match", "concerns": []}]
    stage = LLMScorer(ctx, top_n=1)
    jobs = [make_job(url=f"https://x.example/{i}") for i in range(4)]
    out = stage.run(jobs)
    assert len(llm.prompts) == 1          # the cost model, asserted
    assert len(out) == 1
    assert out[0].score == 0.9 and out[0].rationale == "RL match"


def test_scorer_keeps_jobs_it_failed_to_assess(ctx, llm):
    llm.responses = [{"nonsense": True}]
    stage = LLMScorer(ctx, top_n=1, min_score=0.8)
    out = stage.run([make_job()])
    assert len(out) == 1 and out[0].score is None


def test_scorer_applies_min_score(ctx, llm):
    llm.responses = [{"score": 0.2, "rationale": "wrong field", "concerns": []}]
    assert LLMScorer(ctx, top_n=1, min_score=0.5).run([make_job()]) == []


# --- extract ----------------------------------------------------------------
def test_extract_only_runs_on_unstructured_jobs(ctx, llm):
    structured = make_job()
    assert ExtractStage(ctx).run([structured]) == [structured]
    assert llm.prompts == []


def test_extract_fills_fields_from_raw_text(ctx, llm):
    llm.responses = [{
        "is_job_posting": True,
        "title": "Perception Engineer",
        "location": "Boston, MA",
        "posted_date": "2026-07-01",
        "description": "Own the perception stack.",
        "employment_type": "full-time",
    }]
    job = make_job(title="", description="")
    job.metadata["raw"] = "<h1>Perception Engineer</h1> Boston, MA"
    job.tag(TAG_NEEDS_EXTRACTION)

    out = ExtractStage(ctx).run([job])[0]
    assert out.title == "Perception Engineer"
    assert out.location == "Boston, MA"
    assert str(out.posted_date) == "2026-07-01"
    assert not out.has(TAG_NEEDS_EXTRACTION)
    assert "raw" not in out.metadata


def test_extract_drops_non_postings(ctx, llm):
    llm.responses = [{"is_job_posting": False, "title": "", "location": "",
                      "posted_date": "", "description": "", "employment_type": ""}]
    job = make_job(title="", description="")
    job.metadata["raw"] = "cookie policy"
    job.tag(TAG_NEEDS_EXTRACTION)
    assert ExtractStage(ctx).run([job]) == []


# --- salary -----------------------------------------------------------------
def test_salary_parses_a_range(ctx):
    job = make_job(description="The base salary range is $180,000 - $240,000 per year.")
    SalaryEnricher(ctx).run([job])
    assert job.metadata["salary"] == {"min": 180000, "max": 240000, "period": "annual"}


def test_salary_absent_is_not_an_error(ctx):
    job = make_job(description="Competitive compensation.")
    assert SalaryEnricher(ctx).run([job]) == [job]
    assert "salary" not in job.metadata

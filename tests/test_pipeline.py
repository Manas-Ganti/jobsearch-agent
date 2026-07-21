"""The design rules are the thing worth testing: uniform signature, registry
wiring, and a failing stage not sinking the run."""

from __future__ import annotations

from conftest import make_job

from jobagent.enrichers import ENRICHER_REGISTRY, Enricher
from jobagent.models import canonical_id, canonical_url
from jobagent.pipeline import Pipeline


class Doubler(Enricher):
    name = "doubler"

    def run(self, jobs):
        return jobs + jobs


class Exploding(Enricher):
    name = "exploding"

    def run(self, jobs):
        raise RuntimeError("boom")


def test_pipeline_reduces_in_order(ctx):
    pipeline = Pipeline([Doubler(ctx), Doubler(ctx)])
    assert len(pipeline.run([make_job()])) == 4


def test_failing_stage_passes_data_through(ctx):
    pipeline = Pipeline([Exploding(ctx), Doubler(ctx)])
    out = pipeline.run([make_job()])
    assert len(out) == 2
    assert pipeline.results[0].error is not None
    assert pipeline.results[1].error is None


def test_failing_stage_raises_when_configured(ctx):
    pipeline = Pipeline([Exploding(ctx)], continue_on_error=False)
    try:
        pipeline.run([make_job()])
    except RuntimeError:
        return
    raise AssertionError("expected the stage error to propagate")


def test_every_registered_stage_matches_the_signature(ctx):
    for name in ENRICHER_REGISTRY.names():
        cls = ENRICHER_REGISTRY.get(name)
        assert hasattr(cls, "run"), f"{name} has no run()"
        assert cls.name == name


def test_unknown_stage_name_is_a_clear_error():
    try:
        ENRICHER_REGISTRY.get("does_not_exist")
    except KeyError as exc:
        assert "registered:" in str(exc)
        return
    raise AssertionError("expected KeyError")


def test_canonical_url_ignores_tracking_params():
    a = canonical_url("https://x.example/jobs/1?utm_source=news&gh_src=abc")
    b = canonical_url("https://X.example/jobs/1/")
    assert a == b
    assert canonical_id(a) == canonical_id(b)

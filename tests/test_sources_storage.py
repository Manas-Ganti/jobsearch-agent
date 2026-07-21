from __future__ import annotations

import json

from conftest import make_job

from jobagent.delivery import DeliverStage
from jobagent.models import TAG_NEEDS_EXTRACTION, RawPosting
from jobagent.sources.greenhouse import GreenhouseSource
from jobagent.sources.lever import LeverSource
from jobagent.storage.dedup import DedupStage


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, params=None, use_cache=True):
        self.calls.append(url)
        return self.payload

    def get_text(self, url, params=None, use_cache=True):
        return json.dumps(self.payload)

    def close(self):
        pass


# --- sources ----------------------------------------------------------------
def test_greenhouse_maps_to_raw_postings(ctx):
    ctx.http = FakeHttp({"jobs": [{
        "id": 1,
        "title": "ML Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        "location": {"name": "Remote - US"},
        "content": "&lt;p&gt;Train models&lt;/p&gt;",
        "updated_at": "2026-07-01T10:00:00Z",
    }]})
    postings = GreenhouseSource(ctx, board="acme", company="Acme").fetch()
    assert len(postings) == 1
    assert postings[0].title == "ML Engineer"
    assert postings[0].company == "Acme"
    assert not postings[0].needs_extraction


def test_lever_maps_to_raw_postings(ctx):
    ctx.http = FakeHttp([{
        "text": "Research Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/1",
        "categories": {"location": "NYC", "team": "Research"},
        "descriptionPlain": "Do research.",
        "createdAt": 1751328000000,
        "lists": [{"text": "Requirements", "content": "<li>PyTorch</li>"}],
    }])
    posting = LeverSource(ctx, account="acme").fetch()[0]
    assert posting.title == "Research Engineer"
    assert "PyTorch" in posting.description
    assert posting.metadata["team"] == "Research"


def test_unstructured_raw_posting_is_tagged_for_extraction():
    job = RawPosting(source="browser", company="Acme", url="https://x.example/1",
                     raw="<h1>Engineer</h1>").to_job()
    assert job.has(TAG_NEEDS_EXTRACTION)
    assert job.metadata["raw"]


# --- dedup ------------------------------------------------------------------
def test_dedup_surfaces_only_new_postings(ctx):
    stage = DedupStage(ctx)
    job = make_job()
    assert len(stage.run([job])) == 1
    assert job.has("new")
    assert stage.run([make_job()]) == []          # same posting, second run


def test_dedup_resurfaces_changed_postings(ctx):
    DedupStage(ctx).run([make_job()])
    changed = make_job(description="Now the role also owns evaluation infra.")
    out = DedupStage(ctx).run([changed])
    assert len(out) == 1 and out[0].has("changed")


def test_dedup_records_first_seen(ctx):
    DedupStage(ctx).run([make_job()])
    out = DedupStage(ctx, only_new=False).run([make_job()])
    assert out[0].metadata["first_seen"]


# --- delivery ---------------------------------------------------------------
def test_deliver_passes_jobs_through_and_marks_them(ctx, capsys):
    ctx.config.delivery = {"console": {}}
    job = make_job(score=0.9)
    ctx.db.upsert(job, "fp")

    out = DeliverStage(ctx).run([job])
    assert out == [job]                            # signature preserved
    assert job.title in capsys.readouterr().out
    assert ctx.db.stats()["delivered"] == 1


def test_deliver_skips_disabled_channels(ctx, capsys):
    ctx.config.delivery = {"console": {"enabled": False}}
    DeliverStage(ctx).run([make_job(score=0.9)])
    assert capsys.readouterr().out == ""


def test_deliver_survives_a_broken_channel(ctx, capsys):
    ctx.config.delivery = {"slack": {"webhook_url": ""}, "console": {}}
    job = make_job(score=0.9)
    ctx.db.upsert(job, "fp")
    assert DeliverStage(ctx).run([job]) == [job]
    assert job.title in capsys.readouterr().out

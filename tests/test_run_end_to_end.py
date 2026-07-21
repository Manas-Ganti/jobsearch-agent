"""End-to-end: config.yaml → registries → pipeline → delivered digest.

Uses a source registered here (proving the plugin contract: one file, one
decorator, one config line) and the offline backends, so no server is needed.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from jobagent.models import RawPosting
from jobagent.run import main
from jobagent.sources import BaseSource, register_source


@register_source("fixture")
class FixtureSource(BaseSource):
    def configure(self, company: str = "Fixture Co") -> None:
        self.company = company

    def fetch(self) -> list[RawPosting]:
        return [
            RawPosting(
                source=self.name, company=self.company,
                url="https://fixture.example/jobs/rl",
                title="Research Engineer, Reinforcement Learning",
                location="San Francisco, CA",
                description="Train RL agents with PyTorch. Base range $200,000 - $260,000.",
            ),
            RawPosting(
                source=self.name, company=self.company,
                url="https://fixture.example/jobs/sales",
                title="Enterprise Sales Director",
                location="New York, NY",
                description="Close deals.",
            ),
            RawPosting(
                source=self.name, company=self.company,
                url="https://fixture.example/jobs/cv",
                title="Computer Vision Engineer",
                location="Austin, TX",
                description="Perception stack. We are unable to sponsor visas.",
            ),
        ]


CONFIG = """
profile:
  resume_path: resume.md
  portfolio_path: null

llm: {backend: stub, model: stub}
embeddings: {backend: hashing, model: hashing}
storage: {path: jobs.db}
http: {cache_dir: cache}

sources:
  - type: fixture
    name: fixture
    company: Fixture Co

pipeline: [fetch, keyword_filter, sponsorship, embedding_ranker, llm_scorer, salary, dedup, deliver]

stages:
  keyword_filter:
    include_title: [research engineer, computer vision, machine learning]
    exclude_title: [director]
  llm_scorer: {top_n: 5, min_score: 0.0}
  deliver: {min_score: 0.0}

delivery:
  console: {}
  file: {path: digest.json, format: json}
"""


def _write_project(tmp_path: Path) -> Path:
    (tmp_path / "config.yaml").write_text(textwrap.dedent(CONFIG))
    (tmp_path / "resume.md").write_text("Reinforcement learning and computer vision engineer.")
    return tmp_path / "config.yaml"


def test_full_run_delivers_only_matching_new_jobs(tmp_path, capsys):
    config = _write_project(tmp_path)
    assert main(["-c", str(config), "--offline"]) == 0

    out = capsys.readouterr().out
    assert "Research Engineer, Reinforcement Learning" in out
    assert "Enterprise Sales Director" not in out      # keyword filter
    assert "Computer Vision Engineer" not in out       # sponsorship filter

    digest = json.loads((tmp_path / "digest.json").read_text())
    assert [j["title"] for j in digest] == ["Research Engineer, Reinforcement Learning"]
    assert digest[0]["metadata"]["salary"]["min"] == 200000     # salary enricher ran
    assert digest[0]["metadata"]["first_seen"]                  # dedup ran
    assert (tmp_path / "jobs.db").exists()


def test_second_run_is_quiet(tmp_path, capsys):
    config = _write_project(tmp_path)
    main(["-c", str(config), "--offline"])
    capsys.readouterr()

    main(["-c", str(config), "--offline"])
    assert "Research Engineer" not in capsys.readouterr().out  # dedup did its job


def test_dry_run_does_not_mark_delivered(tmp_path, capsys):
    config = _write_project(tmp_path)
    main(["-c", str(config), "--offline", "--dry-run"])
    out = capsys.readouterr().out
    assert "Research Engineer" in out
    assert not (tmp_path / "digest.json").exists()  # file channel replaced by console

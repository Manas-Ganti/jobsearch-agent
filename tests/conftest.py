from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent.backends.embeddings import HashingEmbeddings  # noqa: E402
from jobagent.config import Config  # noqa: E402
from jobagent.context import Context, Profile  # noqa: E402
from jobagent.http import HttpClient  # noqa: E402
from jobagent.models import JobPosting  # noqa: E402
from jobagent.plugins import discover_all  # noqa: E402
from jobagent.storage import JobStore  # noqa: E402

discover_all()


class ScriptedLLM:
    """LLM double: returns queued JSON payloads, records the prompts it saw."""

    model = "scripted"

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = list(responses or [])
        self.prompts: list[str] = []

    def complete(self, prompt, *, system=None, schema=None) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            return "{}"
        return json.dumps(self.responses.pop(0))


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def ctx(tmp_path, llm) -> Context:
    cfg = Config(root=tmp_path)
    context = Context(
        config=cfg,
        llm=llm,
        embeddings=HashingEmbeddings(),
        db=JobStore(tmp_path / "jobs.db"),
        http=HttpClient(cache_dir=tmp_path / "cache"),
        profile=Profile(resume="reinforcement learning and computer vision engineer"),
    )
    yield context
    context.close()


def make_job(**overrides) -> JobPosting:
    base = dict(
        id="",
        title="Research Engineer, Reinforcement Learning",
        company="Acme AI",
        location="San Francisco, CA",
        url="https://acme.example/jobs/1",
        description="Train RL agents. PyTorch. Vision-language models.",
        source="test",
    )
    base.update(overrides)
    if not base["id"]:
        from jobagent.models import canonical_id

        base["id"] = canonical_id(base["url"])
    return JobPosting(**base)

from __future__ import annotations

import re

from conftest import make_job

from jobagent.delivery.markdown import END, START, MarkdownChannel
from jobagent.delivery.render import as_table


def test_table_has_a_row_per_job_and_links_the_title():
    jobs = [make_job(score=0.91, rationale="RL match"),
            make_job(url="https://x.example/2", title="CV Engineer")]
    table = as_table(jobs)
    lines = table.splitlines()
    assert len(lines) == 4                       # header + separator + 2 rows
    assert "[Research Engineer, Reinforcement Learning](https://acme.example/jobs/1)" in lines[2]
    assert "**0.91**" in lines[2]
    assert "—" in lines[3]                       # unscored job


def test_table_escapes_pipes_and_newlines():
    job = make_job(title="Engineer | RL", rationale="line one\nline two")
    row = as_table([job]).splitlines()[2]
    assert r"Engineer \| RL" in row
    # Only unescaped pipes are cell delimiters: 6 columns → 7 of them.
    assert len(re.findall(r"(?<!\\)\|", row)) == 7
    assert "line one line two" in row


def test_flags_surface_in_the_notes_column():
    job = make_job(score=0.8)
    job.tag("remote")
    job.metadata["salary"] = {"min": 200000, "max": 260000, "period": "annual"}
    row = as_table([job]).splitlines()[2]
    assert "remote" in row and "$200,000–$260,000" in row


def test_channel_replaces_only_the_marked_region(ctx, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(f"# Title\n\nIntro.\n\n{START}\nold table\n{END}\n\nFooter.\n")
    ctx.config.root = tmp_path

    MarkdownChannel(ctx, path="README.md").deliver([make_job(score=0.9)])
    out = readme.read_text()

    assert "old table" not in out
    assert out.startswith("# Title\n\nIntro.\n")
    assert out.rstrip().endswith("Footer.")
    assert "| Score | Role |" in out


def test_channel_appends_when_markers_are_missing(ctx, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Title\n\nIntro.\n")
    ctx.config.root = tmp_path

    MarkdownChannel(ctx, path="README.md").deliver([make_job()])
    out = readme.read_text()
    assert out.startswith("# Title")
    assert START in out and END in out


def test_channel_creates_a_missing_file_and_caps_rows(ctx, tmp_path):
    ctx.config.root = tmp_path
    jobs = [make_job(url=f"https://x.example/{i}") for i in range(10)]
    MarkdownChannel(ctx, path="docs/MATCHES.md", max_rows=3).deliver(jobs)

    out = (tmp_path / "docs" / "MATCHES.md").read_text()
    assert out.count("https://x.example/") == 3
    assert "3 shown" in out


def test_repeated_runs_do_not_stack_blocks(ctx, tmp_path):
    ctx.config.root = tmp_path
    channel = MarkdownChannel(ctx, path="MATCHES.md")
    channel.deliver([make_job()])
    channel.deliver([make_job()])
    out = (tmp_path / "MATCHES.md").read_text()
    assert out.count(START) == 1 and out.count(END) == 1

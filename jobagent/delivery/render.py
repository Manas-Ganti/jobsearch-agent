"""Shared rendering so every channel shows the same digest."""

from __future__ import annotations

from datetime import date
from html import escape

from ..models import JobPosting
from ..textutil import truncate

FLAGS = {
    "no-sponsorship": "⚠ no sponsorship",
    "citizenship-required": "⚠ citizenship required",
    "sponsorship-available": "✓ sponsors visas",
    "remote": "remote",
    "changed": "updated",
}


def _flags(job: JobPosting) -> list[str]:
    out = [FLAGS[t] for t in job.tags if t in FLAGS]
    if salary := job.metadata.get("salary"):
        unit = "/hr" if salary.get("period") == "hourly" else ""
        out.append(f"${salary['min']:,}–${salary.get('max') or salary['min']:,}{unit}")
    return out


def subject(jobs: list[JobPosting]) -> str:
    return f"[jobagent] {len(jobs)} new match{'es' if len(jobs) != 1 else ''} — {date.today():%b %d}"


def as_text(jobs: list[JobPosting]) -> str:
    lines = [subject(jobs), "=" * 60, ""]
    for i, job in enumerate(jobs, 1):
        score = f"{job.score:.2f}" if job.score is not None else " — "
        lines.append(f"{i}. [{score}] {job.title} — {job.company}")
        lines.append(f"   {job.location or 'location not stated'}")
        if flags := _flags(job):
            lines.append(f"   {' · '.join(flags)}")
        if job.rationale:
            lines.append(f"   {truncate(job.rationale, 200)}")
        lines.append(f"   {job.url}")
        lines.append("")
    return "\n".join(lines)


def as_markdown(jobs: list[JobPosting]) -> str:
    lines = [f"*{subject(jobs)}*", ""]
    for job in jobs:
        score = f"{job.score:.2f}" if job.score is not None else "—"
        lines.append(f"*<{job.url}|{job.title}>* — {job.company}  `{score}`")
        meta = [job.location or "location n/a", *_flags(job)]
        lines.append(" · ".join(m for m in meta if m))
        if job.rationale:
            lines.append(f"_{truncate(job.rationale, 200)}_")
        lines.append("")
    return "\n".join(lines)


def as_html(jobs: list[JobPosting]) -> str:
    rows = []
    for job in jobs:
        score = f"{job.score:.2f}" if job.score is not None else "—"
        flags = " · ".join(escape(f) for f in _flags(job))
        rows.append(
            "<li style='margin-bottom:18px'>"
            f"<a href='{escape(job.url)}' style='font-weight:600;font-size:15px'>"
            f"{escape(job.title)}</a> — {escape(job.company)} "
            f"<span style='color:#888'>({score})</span><br>"
            f"<span style='color:#555;font-size:13px'>{escape(job.location or 'location n/a')}"
            f"{' · ' + flags if flags else ''}</span>"
            + (
                f"<br><span style='font-size:13px'>{escape(truncate(job.rationale, 240))}</span>"
                if job.rationale
                else ""
            )
            + "</li>"
        )
    return (
        "<div style='font-family:-apple-system,Segoe UI,sans-serif;max-width:640px'>"
        f"<h2 style='font-size:16px'>{escape(subject(jobs))}</h2>"
        f"<ul style='list-style:none;padding:0'>{''.join(rows)}</ul></div>"
    )

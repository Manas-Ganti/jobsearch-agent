"""Markdown channel — writes the digest as a table, for display on GitHub.

Targets a region of an existing file delimited by HTML comments, so the rest of
your README is never touched:

    <!-- jobagent:start -->
    <!-- jobagent:end -->

If the markers are absent the block is appended; if the file is absent it is
created. GitHub renders the table on the repo page.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from ..models import JobPosting
from . import BaseChannel, register_channel
from .render import as_table

log = logging.getLogger(__name__)

START = "<!-- jobagent:start -->"
END = "<!-- jobagent:end -->"


@register_channel("markdown")
class MarkdownChannel(BaseChannel):
    def configure(
        self,
        path: str = "MATCHES.md",
        heading: str = "## Latest matches",
        max_rows: int = 20,
        include_rationale: bool = True,
        timestamp: bool = True,
    ) -> None:
        self.path = path
        self.heading = heading
        self.max_rows = max_rows
        self.include_rationale = include_rationale
        self.timestamp = timestamp

    def deliver(self, jobs: list[JobPosting]) -> None:
        target = Path(self.path)
        if not target.is_absolute():
            target = self.ctx.config.root / target
        target.parent.mkdir(parents=True, exist_ok=True)

        block = self._block(jobs[: self.max_rows])
        target.write_text(_splice(target.read_text() if target.exists() else "", block))
        log.info("wrote %d rows to %s", min(len(jobs), self.max_rows), target)

    def _block(self, jobs: list[JobPosting]) -> str:
        parts = [START, ""]
        if self.heading:
            parts += [self.heading, ""]
        parts.append(as_table(jobs, include_rationale=self.include_rationale))
        if self.timestamp:
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            parts += ["", f"<sub>Updated {stamp} · {len(jobs)} shown</sub>"]
        parts += ["", END]
        return "\n".join(parts)


def _splice(existing: str, block: str) -> str:
    start, end = existing.find(START), existing.find(END)
    if start != -1 and end != -1 and end > start:
        return existing[:start] + block + existing[end + len(END) :]
    if existing.strip():
        return existing.rstrip() + "\n\n" + block + "\n"
    return block + "\n"

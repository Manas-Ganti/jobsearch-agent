"""Console channel — the default, and what `--dry-run` uses."""

from __future__ import annotations

from ..models import JobPosting
from . import BaseChannel, register_channel
from .render import as_text


@register_channel("console")
class ConsoleChannel(BaseChannel):
    def deliver(self, jobs: list[JobPosting]) -> None:
        print(as_text(jobs))

"""File channel — writes the digest to disk (feeds a dashboard, or just a log)."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from ..models import JobPosting
from . import BaseChannel, register_channel
from .render import as_text

log = logging.getLogger(__name__)


@register_channel("file")
class FileChannel(BaseChannel):
    def configure(self, path: str = "data/digests/{date}.json", format: str = "json") -> None:
        self.path_template = path
        self.format = format

    def deliver(self, jobs: list[JobPosting]) -> None:
        path = Path(self.path_template.format(date=date.today().isoformat()))
        if not path.is_absolute():
            path = self.ctx.config.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.format == "json":
            path.write_text(
                json.dumps([j.model_dump(mode="json") for j in jobs], indent=2)
            )
        else:
            path.write_text(as_text(jobs))
        log.info("wrote digest to %s", path)

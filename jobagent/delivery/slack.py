"""Slack channel — incoming webhook. URL comes from the env via config.yaml."""

from __future__ import annotations

import logging

from ..models import JobPosting
from . import BaseChannel, register_channel
from .render import as_markdown

log = logging.getLogger(__name__)


@register_channel("slack")
class SlackChannel(BaseChannel):
    def configure(self, webhook_url: str = "", chunk_size: int = 10) -> None:
        if not webhook_url:
            raise ValueError("slack channel needs `webhook_url` — set SLACK_WEBHOOK_URL in .env")
        self.webhook_url = webhook_url
        self.chunk_size = chunk_size

    def deliver(self, jobs: list[JobPosting]) -> None:
        # Slack truncates long messages, so send in chunks.
        for i in range(0, len(jobs), self.chunk_size):
            chunk = jobs[i : i + self.chunk_size]
            self.ctx.http.post_json(
                self.webhook_url, {"text": as_markdown(chunk), "mrkdwn": True}
            )
        log.info("posted %d jobs to Slack", len(jobs))

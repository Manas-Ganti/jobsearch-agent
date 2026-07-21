"""Delivery channels + the Deliver stage.

A new channel is: one file in this folder, one `@register_channel` decorator,
one entry under `delivery:` in config.yaml.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ..context import Context
from ..enrichers import Enricher, register_enricher
from ..models import JobPosting
from ..registry import Registry

log = logging.getLogger(__name__)

DELIVERY_REGISTRY: Registry["Channel"] = Registry("delivery channel")
register_channel = DELIVERY_REGISTRY.register


@runtime_checkable
class Channel(Protocol):
    name: str

    def deliver(self, jobs: list[JobPosting]) -> None: ...


class BaseChannel:
    name: str = "channel"

    def __init__(self, ctx: Context, **params: object) -> None:
        self.ctx = ctx
        self.configure(**params)

    def configure(self) -> None:
        """Override to accept config params as keyword arguments."""

    def deliver(self, jobs: list[JobPosting]) -> None:
        raise NotImplementedError


@register_enricher("deliver")
class DeliverStage(Enricher):
    """Fans the final list out to every channel in `delivery:`."""

    def configure(self, min_score: float = 0.0, max_jobs: int = 25, mark_delivered: bool = True) -> None:
        self.min_score = min_score
        self.max_jobs = max_jobs
        self.mark_delivered = mark_delivered
        DELIVERY_REGISTRY.discover(__package__)

    def run(self, jobs: list[JobPosting]) -> list[JobPosting]:
        selected = [j for j in jobs if (j.score or 0.0) >= self.min_score][: self.max_jobs]
        if not selected:
            log.info("nothing to deliver")
            return jobs

        delivered_anywhere = False
        for channel_name, params in (self.ctx.config.delivery or {}).items():
            params = params or {}
            if params.pop("enabled", True) is False:
                continue
            try:
                channel = DELIVERY_REGISTRY.create(channel_name, self.ctx, **params)
                channel.deliver(selected)
                delivered_anywhere = True
                log.info("delivered %d jobs via %s", len(selected), channel_name)
            except Exception as exc:  # a broken channel shouldn't lose the others
                log.error("delivery via %s failed: %s", channel_name, exc)

        if delivered_anywhere and self.mark_delivered:
            self.ctx.db.mark_delivered([j.id for j in selected])
        return jobs


__all__ = ["DELIVERY_REGISTRY", "BaseChannel", "Channel", "DeliverStage", "register_channel"]

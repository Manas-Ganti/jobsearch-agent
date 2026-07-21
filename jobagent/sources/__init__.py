"""Source registry + protocol.

A new job board is: one file in this folder, one `@register_source` decorator,
one entry under `sources:` in config.yaml.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..context import Context
from ..models import RawPosting
from ..registry import Registry

SOURCE_REGISTRY: Registry["Source"] = Registry("source")
register_source = SOURCE_REGISTRY.register


@runtime_checkable
class Source(Protocol):
    name: str

    def fetch(self) -> list[RawPosting]:
        """Return everything currently posted. Filtering happens downstream."""


class BaseSource:
    """Convenience base: holds the context, takes config params as kwargs."""

    name: str = "source"

    def __init__(self, ctx: Context, **params: object) -> None:
        self.ctx = ctx
        self.http = ctx.http
        self.configure(**params)

    def configure(self) -> None:
        """Override to accept config params as keyword arguments."""

    def fetch(self) -> list[RawPosting]:
        raise NotImplementedError


__all__ = ["SOURCE_REGISTRY", "BaseSource", "Source", "register_source"]

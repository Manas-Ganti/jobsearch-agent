"""Plugin discovery.

Stages live in the package they belong to (fetch with the sources, dedup with
the storage, deliver with the channels) but they all register into
`ENRICHER_REGISTRY`, so `pipeline:` in config.yaml is one flat list of names.
"""

from __future__ import annotations

from .backends.embeddings import EMBEDDING_BACKENDS
from .backends.llm import LLM_BACKENDS
from .delivery import DELIVERY_REGISTRY
from .enrichers import ENRICHER_REGISTRY
from .sources import SOURCE_REGISTRY

STAGE_PACKAGES = (
    "jobagent.enrichers",
    "jobagent.sources",   # fetch
    "jobagent.storage",   # dedup
    "jobagent.delivery",  # deliver
)


def discover_all() -> None:
    for package in STAGE_PACKAGES:
        ENRICHER_REGISTRY.discover(package)
    SOURCE_REGISTRY.discover("jobagent.sources")
    DELIVERY_REGISTRY.discover("jobagent.delivery")
    LLM_BACKENDS.discover("jobagent.backends")
    EMBEDDING_BACKENDS.discover("jobagent.backends")


def describe() -> str:
    discover_all()
    blocks = {
        "stages (pipeline:)": ENRICHER_REGISTRY.names(),
        "sources (sources:)": SOURCE_REGISTRY.names(),
        "delivery (delivery:)": DELIVERY_REGISTRY.names(),
        "llm backends": LLM_BACKENDS.names(),
        "embedding backends": EMBEDDING_BACKENDS.names(),
    }
    return "\n".join(f"{k:<22} {', '.join(v)}" for k, v in blocks.items())

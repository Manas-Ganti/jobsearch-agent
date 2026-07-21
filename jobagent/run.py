"""Orchestrator: config → registries → pipeline → execute.

Deliberately boring. It knows about no concrete source, enricher, or channel —
only names it looks up. Adding a feature never touches this file.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .backends import build_embeddings, build_llm
from .config import Config, load_config
from .context import Context, Profile
from .enrichers import ENRICHER_REGISTRY
from .http import HttpClient
from .models import JobPosting
from .pipeline import Pipeline
from .plugins import describe, discover_all
from .storage import JobStore

log = logging.getLogger("jobagent")


def build_context(cfg: Config) -> Context:
    return Context(
        config=cfg,
        llm=build_llm(cfg.llm),
        embeddings=build_embeddings(cfg.embeddings),
        db=JobStore(cfg.path(cfg.storage.path)),
        http=HttpClient(
            cache_dir=cfg.path(cfg.http.cache_dir) if cfg.http.cache_dir else None,
            cache_ttl_seconds=cfg.http.cache_ttl_seconds,
            rate_limit_seconds=cfg.http.rate_limit_seconds,
            timeout_seconds=cfg.http.timeout_seconds,
            user_agent=cfg.http.user_agent,
        ),
        profile=Profile.load(cfg),
    )


def build_pipeline(ctx: Context) -> Pipeline:
    """The whole orchestration: look each stage name up, hand it its params."""
    stages = [
        ENRICHER_REGISTRY.create(name, ctx, **ctx.config.stage_params(name))
        for name in ctx.config.pipeline
    ]
    return Pipeline(stages, continue_on_error=ctx.config.continue_on_error)


def apply_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    """CLI flags are thin overrides on config — never a second wiring path."""
    if args.offline:
        cfg.llm.backend, cfg.embeddings.backend = "stub", "hashing"
    if args.dry_run:
        cfg.delivery = {"console": {}}
        cfg.stages.setdefault("deliver", {})["mark_delivered"] = False
        cfg.stages.setdefault("dedup", {})["only_new"] = False
    if args.sources:
        cfg.stages.setdefault("fetch", {})["only"] = args.sources
    if args.limit:
        cfg.stages.setdefault("fetch", {})["limit_per_source"] = args.limit
    if args.stages:
        cfg.pipeline = args.stages
    return cfg


def run(cfg: Config) -> list[JobPosting]:
    discover_all()
    ctx = build_context(cfg)
    try:
        pipeline = build_pipeline(ctx)
        log.info("pipeline: %s", " → ".join(s.name for s in pipeline.stages))
        jobs = pipeline.run([])
        log.info("\n%s", pipeline.summary())
        return jobs
    finally:
        ctx.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobagent", description="Daily job digest agent")
    parser.add_argument("-c", "--config", default=str(Path(__file__).parent / "config.yaml"))
    parser.add_argument("--dry-run", action="store_true",
                        help="print to console, don't send or mark delivered")
    parser.add_argument("--offline", action="store_true",
                        help="stub LLM + hashing embeddings; no model server needed")
    parser.add_argument("--sources", nargs="*", metavar="NAME",
                        help="only fetch these configured sources")
    parser.add_argument("--stages", nargs="*", metavar="NAME",
                        help="override the pipeline stage list")
    parser.add_argument("--limit", type=int, default=0, help="max postings per source")
    parser.add_argument("--list-plugins", action="store_true", help="show what's registered")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.list_plugins:
        print(describe())
        return 0

    _load_dotenv()
    cfg = apply_overrides(load_config(args.config), args)
    jobs = run(cfg)
    log.info("done — %d job(s) survived the pipeline", len(jobs))
    return 0


def _load_dotenv() -> None:
    """Secrets come from the env; .env is a convenience, not a requirement."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


if __name__ == "__main__":
    sys.exit(main())

# CLAUDE.md

Guidance for working in this repo. Read this before adding code.

## What this is

A personal job-hunting agent. Once a day it fetches postings from configured
job boards and company career pages, extracts them into a structured form,
ranks and scores them against the user's resume and portfolio, deduplicates
against previously seen jobs, and delivers the new matches.

Runs as a daily batch (GitHub Actions cron or local `launchd`/cron). One user,
modest volume, no realtime requirements. Optimize for **modularity and low cost**,
not throughput.

## Non-negotiable design rules

These are the load-bearing decisions. Do not violate them when adding features.

1. **One shared data contract.** Every pipeline stage reads and writes
   `list[JobPosting]` (see `models.py`). Never invent a parallel job shape.
   Feature-specific data goes in the `metadata: dict` and `tags: list[str]`
   escape hatches, never as new top-level fields unless the field is universal.

2. **Uniform stage signature.** Every stage implements
   `run(jobs: list[JobPosting]) -> list[JobPosting]`. The pipeline is an
   ordered list of stages reduced over the data. Adding, removing, or
   reordering a feature must be a one-line edit to the pipeline list — never
   a change to the orchestrator's control flow.

3. **Registries for the extension points.** Sources and enrichers self-register
   via decorators. A new source or enricher is **one new file + one decorator +
   one config line**. The orchestrator must never `import` a concrete source or
   enricher directly.

4. **Backends behind protocols.** All model inference (LLM, embeddings) goes
   through `LLMBackend` / `EmbeddingBackend` protocols. Pipeline code must never
   know whether it is talking to Ollama, vLLM, or an API. Swapping models is a
   config change.

5. **Config is the wiring.** What runs, in what order, with which model, and
   where results go is declared in `config.yaml`. Enabling or reordering a
   feature should not require editing Python.

If a change would break one of these rules, stop and reconsider the design
rather than working around it.

## Models / cost stance

Use **open-source models**, self-hosted. Default to the cheapest thing that works.

- LLM work (extraction, scoring): a 7B–14B instruct model (e.g. Qwen2.5-7B).
  Served via Ollama for the local default, vLLM for batch/GPU runs.
- Ranking: embeddings (e.g. BGE) for a cheap first-pass, cosine vs. the resume.
- **Only LLM-score the top N** candidates after embedding-ranking. Never send
  every posting to the LLM — that defeats the cost model.
- Extraction must use **JSON-constrained decoding** (Ollama `format: json`,
  or vLLM guided decoding) so parsing never breaks on malformed output.

## Architecture

```
config.yaml  ──►  run.py  ──►  builds pipeline from registries + config
                                │
        list[JobPosting] flows through ordered stages:

   Fetch ─► Extract ─► KeywordFilter ─► EmbeddingRanker ─► LLMScorer
         ─► [enrichers…] ─► Dedup ─► Deliver
```

- **Fetch** — per-source adapters. API sources (Greenhouse, Lever, Ashby) via
  `httpx`. Browser sources (JS-heavy career pages) via Playwright / Kernel.sh.
  Prefer structured API endpoints; use the browser only when there's no API.
- **Extract** — LLM turns raw HTML/text into `JobPosting` objects. Only needed
  for unstructured (browser) sources; API sources map directly.
- **KeywordFilter** — cheap title/location prefilter, no model. Discards obvious
  non-matches before any expensive step.
- **EmbeddingRanker** — embed postings + resume, rank by cosine similarity.
- **LLMScorer** — LLM scores only the top N survivors against resume + portfolio,
  emits `score` (0–1) and a one-line `rationale`.
- **Enrichers** — optional stages that read a `JobPosting` and add to it
  (sponsorship flag, salary parse, seniority class, etc.). This is where most
  new features live.
- **Dedup** — hash on canonical URL or `(company, title, location)`. Track
  `first_seen` so daily runs surface only new/changed postings.
- **Deliver** — email / Slack / dashboard. Each channel is a plugin.

## Directory layout

```
jobagent/
  models.py            # JobPosting, RawPosting — the shared contracts
  pipeline.py          # Stage protocol + reduce-based runner
  backends/
    llm.py             # LLMBackend protocol + Ollama/vLLM impls
    embeddings.py      # EmbeddingBackend protocol + impls
  sources/
    __init__.py        # SOURCE_REGISTRY + register_source decorator
    greenhouse.py
    lever.py
    browser.py
  enrichers/
    __init__.py        # ENRICHER_REGISTRY + register_enricher decorator
    keyword_filter.py
    embedding_ranker.py
    llm_scorer.py
    sponsorship.py     # ← new features land here
  storage/
    db.py              # SQLite, dedup, first_seen tracking
  delivery/
    email.py
    slack.py
  config.yaml
  run.py               # wires config → registries → pipeline → execute
```

Each subfolder under `sources/`, `enrichers/`, and `delivery/` is a plugin point.
Adding a feature should mean adding a file to one of these folders — not editing
`run.py` or `pipeline.py`.

## Adding things

**A new job board:**
1. Add `sources/<name>.py`.
2. Implement the `Source` protocol; decorate the class with `@register_source("<name>")`.
3. Reference it in `config.yaml` under `sources:` with its `type` and params.
No other file changes.

**A new enricher / filter (e.g. salary parser, seniority classifier):**
1. Add `enrichers/<name>.py` implementing the `Enricher`/`Stage` interface.
2. Decorate with `@register_enricher("<name>")`.
3. Add its name to the `pipeline:` list in `config.yaml` at the position you want.
No other file changes.

**A new delivery channel:**
1. Add `delivery/<name>.py`.
2. Register it; add to `delivery:` in `config.yaml`.

**Swapping a model or backend:**
Edit `config.yaml` (`llm.backend`, `llm.model`, `embeddings.*`). If it's a new
backend kind, add an impl in `backends/` behind the existing protocol.

## Data contract (reference)

```python
class JobPosting(BaseModel):
    id: str                      # canonical hash — set by Dedup/Fetch
    title: str
    company: str
    location: str
    url: str
    description: str
    posted_date: date | None
    source: str
    # enrichment — all optional, filled by later stages
    score: float | None = None
    rationale: str | None = None
    tags: list[str] = []         # e.g. "no-sponsorship", "remote"
    metadata: dict = {}          # source-/feature-specific escape hatch
```

New features attach to `tags` / `metadata`. Promote a field to top-level only
when it's genuinely universal across all jobs.

## Conventions

- Python, type hints throughout, Pydantic for the contracts.
- Stages must be **pure w.r.t. their signature**: take `list[JobPosting]`,
  return `list[JobPosting]`. Side effects (DB writes, sending mail) are fine
  inside `Dedup`/`Deliver` but the data still flows through unchanged where
  it makes sense.
- Fetch politely: rate-limit, cache raw responses so a downstream failure
  doesn't re-hit every site.
- Never scrape sources whose ToS forbid it (LinkedIn, Indeed) — use their APIs
  or skip them.
- Keep secrets (SMTP creds, Slack webhook, any API keys) out of the repo; load
  from env / a gitignored `.env`.

## User context

The user is on an F-1 visa. Sponsorship matters — a `sponsorship` enricher
should tag/down-rank postings that state no sponsorship. Target roles skew
toward RL, VLM, computer vision, and ML/research engineering; the resume and
portfolio provided to the scorer reflect that.
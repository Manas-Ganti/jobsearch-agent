# jobsearch-agent

A personal job-hunting agent. Once a day it fetches postings from job boards and
career pages, filters and ranks them against your resume, scores the finalists
with a local LLM, drops anything you've already seen, and delivers the rest.

Self-hosted, open-source models only. The expensive stage sees ~15 postings a
day, not ~2000.

```
fetch → extract → keyword_filter → sponsorship → embedding_ranker → llm_scorer → salary → dedup → deliver
 1912      1912         112            112             40                15         15      new     inbox
```

## Quick start

```bash
pip install -e '.[dev]'

# 1. Put your real resume here — it's the only description of you the agent sees.
$EDITOR profile/resume.md profile/portfolio.md

# 2. See the whole pipeline run with no model server and nothing sent:
python -m jobagent.run --dry-run --offline

# 3. Point it at your boards, then run for real (needs Ollama, below).
$EDITOR jobagent/config.yaml
python -m jobagent.run --dry-run
```

`--offline` swaps in a stub LLM and hashed embeddings so you can exercise the
plumbing without a model server. Scores from it are meaningless by design —
use it to check wiring, not matches.

### Models

```bash
brew install ollama && ollama serve
ollama pull qwen2.5:7b-instruct   # extraction + scoring
ollama pull bge-m3                # embeddings
```

Both are named in `config.yaml`; swapping to vLLM or a different model is a
config edit, never a code change.

### Delivery

```bash
cp .env.example .env      # gitignored; config.yaml reads ${VARS} from it
```

Then flip `enabled: true` under `delivery.email` or `delivery.slack` in
`config.yaml`. `console` and `file` need no credentials.

## Daily runs

**launchd/cron (local):**
```
0 8 * * *  cd ~/portfolio-projects/jobsearch-agent && /usr/bin/python3 -m jobagent.run >> data/run.log 2>&1
```

**GitHub Actions:** `.github/workflows/daily.yml` is set up but disabled by
default — it can't reach a self-hosted Ollama, so either point `llm.base_url` at
a reachable server or run it on a self-hosted runner.

## CLI

| flag | effect |
|---|---|
| `--dry-run` | console only, nothing sent, nothing marked delivered |
| `--offline` | stub LLM + hashing embeddings, no server needed |
| `--sources a b` | only fetch these configured sources |
| `--stages a b` | override the pipeline list for one run |
| `--limit N` | cap postings per source |
| `--list-plugins` | show every registered stage, source, channel, backend |

## Adding things

Everything below is "one file + one decorator + one config line". `run.py` and
`pipeline.py` never change.

**A job board** — `jobagent/sources/<name>.py`:
```python
@register_source("myboard")
class MyBoardSource(BaseSource):
    def configure(self, board: str = "") -> None:
        self.board = board

    def fetch(self) -> list[RawPosting]:
        data = self.http.get_json(f"https://api.example/{self.board}/jobs")
        return [RawPosting(source=self.name, company="Example", url=j["url"],
                           title=j["title"], description=j["body"]) for j in data]
```
```yaml
sources:
  - {type: myboard, name: example, board: example-co}
```

Fetch through `self.http` — it rate-limits per host and caches raw responses, so
a failure downstream doesn't re-hit every site. If a board has no API, use the
`browser` source; postings from it arrive unstructured and the `extract` stage
turns them into fields.

**A filter or enricher** — `jobagent/enrichers/<name>.py`:
```python
@register_enricher("seniority")
class SeniorityEnricher(Enricher):
    def configure(self, max_years: int = 5) -> None:
        self.max_years = max_years

    def process(self, job: JobPosting) -> JobPosting | None:
        ...                      # return None to drop the job
        return job.tag("senior")
```
```yaml
pipeline: [fetch, keyword_filter, seniority, embedding_ranker, llm_scorer, dedup, deliver]
```
Position matters: free stages belong before paid ones. Override `run()` instead
of `process()` when the stage needs the whole list.

**A delivery channel** — `jobagent/delivery/<name>.py`, `@register_channel`,
then an entry under `delivery:`.

## Design rules this enforces

1. One data contract — every stage takes and returns `list[JobPosting]`.
   Feature data goes in `tags` / `metadata`, never new top-level fields.
2. Uniform stage signature — the pipeline is a `reduce` over an ordered list, so
   reordering a feature is a one-line config edit.
3. Registries at every extension point — the orchestrator imports no concrete
   source, enricher, or channel.
4. Backends behind protocols — pipeline code never learns whether it's talking
   to Ollama or vLLM.
5. Config is the wiring — what runs, in what order, with which model, and where
   it goes all live in `config.yaml`.

Tests in `tests/` assert the rules themselves (a failing stage can't sink a run;
the scorer never exceeds `top_n` LLM calls), not just the happy paths.

```bash
python -m pytest
```

## Notes

- **Sponsorship** runs before any paid stage and drops postings that state no
  sponsorship or require citizenship/clearance. Matches are recorded in
  `metadata["sponsorship"]["evidence"]` so a wrong drop is debuggable; set
  `drop_no_sponsorship: false` to tag instead of drop.
- **Never point a source at a site whose terms forbid it** (LinkedIn, Indeed).
  Use official APIs or skip them.
- State lives in `data/` (SQLite + response cache), which is gitignored. Delete
  `data/jobs.db` to make everything look new again.

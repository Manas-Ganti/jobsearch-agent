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

<!-- jobagent:start -->

## Latest matches

| Score | Role | Company | Location | Notes | Why |
|---|---|---|---|---|---|
| — | [Research Engineer, Frontier Evals & Environments](https://jobs.ashbyhq.com/openai/bba18df5-f30f-4d2c-909c-30e651f95579) | OpenAI | San Francisco | — | — |
| — | [Machine Learning Engineer, Integrity](https://jobs.ashbyhq.com/openai/ecf1abec-898c-4acb-a984-42858836a1ff) | OpenAI | San Francisco | — | — |
| — | [AI Engineer - FDE (Forward Deployed Engineer)](https://databricks.com/company/careers/open-positions/job?gh_jid=8099751002) | Databricks | Remote - India | remote | — |
| — | [AI Engineer - FDE (Forward Deployed Engineer)](https://databricks.com/company/careers/open-positions/job?gh_jid=8546367002) | Databricks | United States | $152,900–$210,155 | — |
| — | [AI Engineer - FDE (Forward Deployed Engineer)](https://databricks.com/company/careers/open-positions/job?gh_jid=8593713002) | Databricks | Remote - United Kingdom | remote | — |
| — | [Anthropic Fellows Program, AI Safety](https://job-boards.greenhouse.io/anthropic/jobs/5183044008) | Anthropic | London, UK; Ontario, CAN; Remote-Friendly, United States; San Francisco, CA | remote · ✓ sponsors visas | — |
| — | [Anthropic Fellows Program, Reinforcement Learning](https://job-boards.greenhouse.io/anthropic/jobs/5183052008) | Anthropic | London, UK; Ontario, CAN; Remote-Friendly, United States; San Francisco, CA | remote · ✓ sponsors visas | — |
| — | [Anthropic Fellows Program, AI Security](https://job-boards.greenhouse.io/anthropic/jobs/5030244008) | Anthropic | London, UK; Ontario, CAN; Remote-Friendly, United States; San Francisco, CA | remote · ✓ sponsors visas | — |
| — | [AI Deployment Engineer, Startups](https://jobs.ashbyhq.com/openai/f92d5695-306d-4af2-8d8b-a09259dd626a) | OpenAI | New York City | — | — |
| — | [Research Engineer, Retrieval & Search, Applied Engineering](https://jobs.ashbyhq.com/openai/7322d344-9325-4a92-8445-0a2c4e9272f8) | OpenAI | San Francisco | — | — |
| — | [Research Engineer / Research Scientist- Personal AGI (Post Training)](https://jobs.ashbyhq.com/openai/1c516e9f-c97d-4a40-8529-9871dac615a5) | OpenAI | San Francisco | — | — |
| — | [Research Scientist](https://jobs.ashbyhq.com/openai/5f0c6579-0bfb-4a06-8a43-1dd371499e10) | OpenAI | San Francisco | — | — |
| — | [Researcher, Trustworthy AI](https://jobs.ashbyhq.com/openai/71acba5c-dbae-406f-b983-f40943c43068) | OpenAI | San Francisco | — | — |
| — | [Research Engineer](https://jobs.ashbyhq.com/openai/240d459b-696d-43eb-8497-fab3e56ecd9b) | OpenAI | San Francisco | — | — |
| — | [Applied AI Architect, Commercial](https://job-boards.greenhouse.io/anthropic/jobs/5192805008) | Anthropic | San Francisco, CA \| New York City, NY | ✓ sponsors visas · $240,000–$315,000 | — |
| — | [Applied AI Architect, Partnerships](https://job-boards.greenhouse.io/anthropic/jobs/5300430008) | Anthropic | San Francisco, CA \| New York City, NY | ✓ sponsors visas · $275,000–$380,000 | — |
| — | [Applied AI Technical Evangelist, Startup Ecosystem](https://job-boards.greenhouse.io/anthropic/jobs/5116927008) | Anthropic | San Francisco, CA | ✓ sponsors visas · $240,000–$315,000 | — |
| — | [Applied AI Architect, Enterprise Tech](https://job-boards.greenhouse.io/anthropic/jobs/5065835008) | Anthropic | Boston, MA; New York City, NY; San Francisco, CA \| New York City, NY; Seattle, WA | ✓ sponsors visas · $240,000–$315,000 | — |
| — | [Applied AI Architect, Industries](https://job-boards.greenhouse.io/anthropic/jobs/4461444008) | Anthropic | New York City, NY; San Francisco, CA \| New York City, NY \| Seattle, WA | ✓ sponsors visas · $240,000–$315,000 | — |

<sub>Updated 2026-07-21 18:17 UTC · 19 shown</sub>

<!-- jobagent:end -->

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
`config.yaml`. `console`, `file`, and `markdown` need no credentials.

The **markdown** channel is what renders the table at the top of this file. It
rewrites only the region between the `<!-- jobagent:start -->` and
`<!-- jobagent:end -->` markers, so the rest of the README is untouched — point
`delivery.markdown.path` at any file, or set `include_rationale: false` to drop
the LLM's commentary from a public page. Commit the file for it to show on
GitHub; the digest itself is never committed automatically.

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

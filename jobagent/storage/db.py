"""SQLite: dedup + first_seen tracking, so a daily run surfaces only new work."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..models import JobPosting

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    company      TEXT NOT NULL,
    title        TEXT NOT NULL,
    location     TEXT,
    source       TEXT,
    fingerprint  TEXT,
    score        REAL,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    delivered_at TEXT,
    payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobStore:
    def __init__(self, path: str | Path = "data/jobs.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- dedup ---------------------------------------------------------------
    def seen(self, job_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()

    def upsert(self, job: JobPosting, fingerprint: str) -> tuple[bool, bool]:
        """Record a sighting. Returns (is_new, changed)."""
        now = _now()
        row = self.seen(job.id)
        payload = job.model_dump_json()
        if row is None:
            self.conn.execute(
                "INSERT INTO jobs (id, url, company, title, location, source, "
                "fingerprint, score, first_seen, last_seen, payload) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job.id, job.url, job.company, job.title, job.location, job.source,
                    fingerprint, job.score, now, now, payload,
                ),
            )
            self.conn.commit()
            return True, False
        changed = row["fingerprint"] != fingerprint
        self.conn.execute(
            "UPDATE jobs SET last_seen=?, fingerprint=?, score=?, payload=?, "
            "title=?, location=? WHERE id=?",
            (now, fingerprint, job.score, payload, job.title, job.location, job.id),
        )
        self.conn.commit()
        return False, changed

    def first_seen(self, job_id: str) -> str | None:
        row = self.seen(job_id)
        return row["first_seen"] if row else None

    # -- delivery ------------------------------------------------------------
    def mark_delivered(self, job_ids: list[str]) -> None:
        now = _now()
        self.conn.executemany(
            "UPDATE jobs SET delivered_at=? WHERE id=?", [(now, i) for i in job_ids]
        )
        self.conn.commit()

    def undelivered(self, limit: int = 100) -> list[JobPosting]:
        rows = self.conn.execute(
            "SELECT payload FROM jobs WHERE delivered_at IS NULL "
            "ORDER BY score DESC NULLS LAST LIMIT ?",
            (limit,),
        ).fetchall()
        return [JobPosting.model_validate(json.loads(r["payload"])) for r in rows]

    def stats(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) n, SUM(delivered_at IS NOT NULL) delivered FROM jobs"
        ).fetchone()
        return {"total": row["n"], "delivered": row["delivered"] or 0}

    def close(self) -> None:
        self.conn.close()

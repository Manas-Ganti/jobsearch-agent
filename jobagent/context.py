"""Everything a stage may need, assembled once in run.py and passed in.

Stages get the shared resources through this object rather than importing
concrete backends, which is what keeps rule 4 (backends behind protocols) true.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .backends import EmbeddingBackend, LLMBackend
from .config import Config
from .http import HttpClient
from .storage import JobStore
from .textutil import normalize_text

log = logging.getLogger(__name__)


def read_pdf(path: Path) -> str:
    """Resumes are usually PDFs. Reading one directly keeps the real document
    out of the repo — point `profile.resume_path` at it and gitignore it."""
    try:
        from pypdf import PdfReader
    except ImportError:
        log.error(
            "%s is a PDF but pypdf is not installed — pip install 'jobsearch-agent[pdf]'",
            path,
        )
        return ""
    try:
        pages = PdfReader(str(path)).pages
    except Exception as exc:
        log.error("could not read %s: %s", path, exc)
        return ""
    return normalize_text("\n".join(page.extract_text() or "" for page in pages))


@dataclass
class Profile:
    """The user's side of the match: what the scorer compares postings against."""

    resume: str = ""
    portfolio: str = ""

    @property
    def text(self) -> str:
        parts = [p for p in (self.resume, self.portfolio) if p.strip()]
        return "\n\n".join(parts)

    @classmethod
    def load(cls, cfg: Config) -> "Profile":
        def read(rel: str | None) -> str:
            if not rel:
                return ""
            path = cfg.path(rel)
            if not path.exists():
                log.warning("profile file missing: %s", path)
                return ""
            text = read_pdf(path) if path.suffix.lower() == ".pdf" else path.read_text()
            if not text.strip():
                log.warning("profile file is empty after reading: %s", path)
            return text

        return cls(read(cfg.profile.resume_path), read(cfg.profile.portfolio_path))


@dataclass
class Context:
    config: Config
    llm: LLMBackend
    embeddings: EmbeddingBackend
    db: JobStore
    http: HttpClient
    profile: Profile

    def close(self) -> None:
        self.http.close()
        self.db.close()

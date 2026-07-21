"""config.yaml → typed config. This file is the wiring; Python is not."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand(value: Any) -> Any:
    """Expand ${VAR} / ${VAR:-default} so secrets live in the env, not the repo."""
    if isinstance(value, str):
        return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


class BackendConfig(BaseModel):
    backend: str = "ollama"
    model: str = "qwen2.5:7b-instruct"
    base_url: str = "http://localhost:11434"
    options: dict = Field(default_factory=dict)


class ProfileConfig(BaseModel):
    resume_path: str = "profile/resume.md"
    portfolio_path: str | None = "profile/portfolio.md"


class StorageConfig(BaseModel):
    path: str = "data/jobs.db"


class HttpConfig(BaseModel):
    cache_dir: str | None = "data/cache"
    cache_ttl_seconds: int = 6 * 3600
    rate_limit_seconds: float = 1.0
    timeout_seconds: float = 30.0
    user_agent: str = "jobsearch-agent/0.1 (personal job alerts; contact via repo owner)"


class SourceConfig(BaseModel):
    type: str
    name: str | None = None
    params: dict = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    def build_params(self) -> dict:
        """Anything not `type`/`name`/`params` is treated as a param, so config
        can stay flat for simple sources."""
        extra = {
            k: v
            for k, v in (self.__pydantic_extra__ or {}).items()
            if k not in {"type", "name", "params"}
        }
        return {**extra, **self.params}


class Config(BaseModel):
    profile: ProfileConfig = Field(default_factory=ProfileConfig)
    llm: BackendConfig = Field(default_factory=BackendConfig)
    embeddings: BackendConfig = Field(
        default_factory=lambda: BackendConfig(model="bge-m3")
    )
    storage: StorageConfig = Field(default_factory=StorageConfig)
    http: HttpConfig = Field(default_factory=HttpConfig)

    sources: list[SourceConfig] = Field(default_factory=list)
    pipeline: list[str] = Field(default_factory=list)
    stages: dict[str, dict] = Field(default_factory=dict)
    delivery: dict[str, dict] = Field(default_factory=dict)

    continue_on_error: bool = True
    root: Path = Path(".")

    def path(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else self.root / p

    def stage_params(self, name: str) -> dict:
        return dict(self.stages.get(name) or {})


def load_config(path: str | Path) -> Config:
    path = Path(path).expanduser().resolve()
    data = yaml.safe_load(path.read_text()) or {}
    cfg = Config.model_validate(_expand(data))
    cfg.root = _project_root(path.parent)
    return cfg


def _project_root(config_dir: Path) -> Path:
    """Relative paths in config resolve against the project root, so a cron job
    can run from anywhere. config.yaml ships inside the package, so step out of
    it: `jobagent/config.yaml` → paths are relative to the repo root."""
    return config_dir.parent if (config_dir / "__init__.py").exists() else config_dir

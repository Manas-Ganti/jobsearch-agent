"""Polite HTTP: per-host rate limiting + on-disk cache of raw responses.

Caching raw responses means a downstream failure (bad LLM output, delivery
error) does not re-hit every site on the next run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)


class HttpClient:
    def __init__(
        self,
        cache_dir: str | Path | None = "data/cache",
        cache_ttl_seconds: int = 6 * 3600,
        rate_limit_seconds: float = 1.0,
        timeout_seconds: float = 30.0,
        user_agent: str = "jobsearch-agent/0.1",
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl_seconds
        self.rate_limit = rate_limit_seconds
        self._last_hit: dict[str, float] = {}
        self._client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )

    # -- cache ---------------------------------------------------------------
    def _cache_path(self, method: str, url: str, body: object) -> Path | None:
        if not self.cache_dir:
            return None
        key = hashlib.sha256(
            f"{method}|{url}|{json.dumps(body, sort_keys=True, default=str)}".encode()
        ).hexdigest()[:24]
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, path: Path | None) -> str | None:
        if not path or not path.exists():
            return None
        if self.cache_ttl and time.time() - path.stat().st_mtime > self.cache_ttl:
            return None
        return json.loads(path.read_text())["body"]

    def cache_get(self, key: str) -> str | None:
        """Cache access for fetchers that don't go through httpx (e.g. browser)."""
        return self._read_cache(self._cache_path("RAW", key, None))

    def cache_put(self, key: str, body: str) -> None:
        path = self._cache_path("RAW", key, None)
        if path:
            path.write_text(json.dumps({"url": key, "body": body}))

    # -- requests ------------------------------------------------------------
    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        wait = self.rate_limit - (time.monotonic() - self._last_hit.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def get_text(self, url: str, *, params: dict | None = None, use_cache: bool = True) -> str:
        path = self._cache_path("GET", url, params) if use_cache else None
        cached = self._read_cache(path)
        if cached is not None:
            log.debug("cache hit %s", url)
            return cached
        self._throttle(url)
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        if path:
            path.write_text(json.dumps({"url": url, "body": resp.text}))
        return resp.text

    def get_json(self, url: str, *, params: dict | None = None, use_cache: bool = True):
        return json.loads(self.get_text(url, params=params, use_cache=use_cache))

    def post_json(self, url: str, json_body: dict) -> dict:
        """Uncached — used by delivery channels (webhooks), not by fetching."""
        self._throttle(url)
        resp = self._client.post(url, json=json_body)
        resp.raise_for_status()
        return resp.json() if resp.content and resp.headers.get(
            "content-type", ""
        ).startswith("application/json") else {}

    def close(self) -> None:
        self._client.close()

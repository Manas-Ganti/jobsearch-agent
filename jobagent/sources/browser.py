"""Browser source for JS-heavy career pages that expose no API.

Last resort — prefer a structured endpoint whenever one exists. Postings from
here come back unstructured and are turned into fields by the Extract stage.

Only point this at pages whose terms permit it (never LinkedIn/Indeed).
Requires the optional extra:  pip install 'jobsearch-agent[browser]' && playwright install chromium
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

from ..models import RawPosting
from . import BaseSource, register_source

log = logging.getLogger(__name__)


@register_source("browser")
class BrowserSource(BaseSource):
    def configure(
        self,
        url: str = "",
        company: str = "",
        link_selector: str | None = None,
        content_selector: str | None = None,
        max_jobs: int = 25,
        wait_until: str = "networkidle",
        timeout_ms: int = 30000,
    ) -> None:
        if not url or not company:
            raise ValueError("browser source needs `url` and `company`")
        self.url = url
        self.company = company
        self.link_selector = link_selector
        self.content_selector = content_selector
        self.max_jobs = max_jobs
        self.wait_until = wait_until
        self.timeout_ms = timeout_ms

    def fetch(self) -> list[RawPosting]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:  # pragma: no cover - optional dependency
            log.error(
                "browser source %s skipped: playwright not installed "
                "(pip install 'jobsearch-agent[browser]')",
                self.company,
            )
            return []

        postings: list[RawPosting] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(user_agent=self.ctx.config.http.user_agent)
            try:
                links = self._collect_links(page)
                for link in links[: self.max_jobs]:
                    text = self._page_text(page, link)
                    if text:
                        postings.append(
                            RawPosting(
                                source=self.name,
                                company=self.company,
                                url=link,
                                raw=text,
                                metadata={"listing_url": self.url},
                            )
                        )
            finally:
                browser.close()
        log.info("browser:%s → %d postings", self.company, len(postings))
        return postings

    def _collect_links(self, page) -> list[str]:
        if not self.link_selector:
            return [self.url]
        page.goto(self.url, wait_until=self.wait_until, timeout=self.timeout_ms)
        hrefs = page.eval_on_selector_all(
            self.link_selector, "els => els.map(e => e.getAttribute('href'))"
        )
        seen: dict[str, None] = {}
        for href in hrefs:
            if href:
                seen.setdefault(urljoin(self.url, href), None)
        return list(seen)

    def _page_text(self, page, link: str) -> str:
        cached = self.http.cache_get(link)
        if cached is not None:
            return cached
        try:
            page.goto(link, wait_until=self.wait_until, timeout=self.timeout_ms)
            selector = self.content_selector or "body"
            text = page.inner_text(selector)
        except Exception as exc:  # one bad page shouldn't kill the source
            log.warning("browser fetch failed for %s: %s", link, exc)
            return ""
        self.http.cache_put(link, text)
        return text

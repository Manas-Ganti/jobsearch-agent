"""Salary: parse a pay range out of the description into `metadata["salary"]`.

Second worked example of the enricher plugin point — regex only, no model.
"""

from __future__ import annotations

import re

from ..models import JobPosting
from . import Enricher, register_enricher

_AMOUNT = r"\$\s?(\d{2,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?\s?[kK]|\d{5,7})"
RANGE = re.compile(rf"{_AMOUNT}\s*(?:-|–|—|to)\s*{_AMOUNT}")
SINGLE = re.compile(_AMOUNT)
HOURLY = re.compile(r"\bper\s+hour\b|\bhourly\b|/\s?hr\b", re.I)


def _to_number(raw: str) -> int:
    text = raw.replace(",", "").replace("$", "").strip()
    if text[-1] in "kK":
        return int(float(text[:-1].strip()) * 1000)
    return int(float(text))


@register_enricher("salary")
class SalaryEnricher(Enricher):
    def configure(self, min_annual: int = 0, drop_below_min: bool = False) -> None:
        self.min_annual = min_annual
        self.drop_below_min = drop_below_min

    def process(self, job: JobPosting) -> JobPosting | None:
        text = job.description
        low = high = None
        if m := RANGE.search(text):
            low, high = _to_number(m.group(1)), _to_number(m.group(2))
        elif m := SINGLE.search(text):
            low = high = _to_number(m.group(1))

        if low is None:
            return job

        period = "hourly" if HOURLY.search(text[max(0, m.start() - 60) : m.end() + 60]) else "annual"
        job.metadata["salary"] = {"min": low, "max": high, "period": period}
        job.tag("salary-listed")

        if period == "annual" and self.min_annual and (high or low) < self.min_annual:
            job.tag("below-salary-floor")
            if self.drop_below_min:
                return None
        return job

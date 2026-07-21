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

# A dollar figure in a job post is often *not* pay: compute budgets, equipment
# stipends, education allowances. Only trust an amount that sits near a
# compensation cue — a missing salary beats a wrong one.
CUE = re.compile(
    r"\b(salary|compensation|pay\s+range|pay\s+transparency|base\s+pay|base\s+range|"
    r"total\s+comp\w*|remuneration|annual\s+pay|expected\s+pay|hourly\s+rate)\b",
    re.I,
)
CUE_WINDOW = 220

PERIODS = (
    (re.compile(r"\bper\s+hour\b|\bhourly\b|/\s?hr\b", re.I), "hourly"),
    (re.compile(r"\bper\s+month\b|\bmonthly\b|/\s?mo(nth)?\b", re.I), "monthly"),
    (re.compile(r"\bper\s+week\b|\bweekly\b|/\s?wk\b", re.I), "weekly"),
)


def _to_number(raw: str) -> int:
    text = raw.replace(",", "").replace("$", "").strip()
    if text[-1] in "kK":
        return int(float(text[:-1].strip()) * 1000)
    return int(float(text))


def _first_with_cue(pattern: re.Pattern, text: str) -> re.Match | None:
    """First match preceded by a compensation cue within CUE_WINDOW chars."""
    for match in pattern.finditer(text):
        if CUE.search(text[max(0, match.start() - CUE_WINDOW) : match.start()]):
            return match
    return None


def _period(text: str, match: re.Match) -> str:
    window = text[max(0, match.start() - 80) : match.end() + 80]
    for pattern, name in PERIODS:
        if pattern.search(window):
            return name
    return "annual"


@register_enricher("salary")
class SalaryEnricher(Enricher):
    def configure(self, min_annual: int = 0, drop_below_min: bool = False) -> None:
        self.min_annual = min_annual
        self.drop_below_min = drop_below_min

    def process(self, job: JobPosting) -> JobPosting | None:
        text = job.description
        match = _first_with_cue(RANGE, text) or _first_with_cue(SINGLE, text)
        if match is None:
            return job

        low = _to_number(match.group(1))
        high = _to_number(match.group(2)) if match.re is RANGE else low

        period = _period(text, match)
        job.metadata["salary"] = {"min": low, "max": high, "period": period}
        job.tag("salary-listed")

        if period == "annual" and self.min_annual and (high or low) < self.min_annual:
            job.tag("below-salary-floor")
            if self.drop_below_min:
                return None
        return job

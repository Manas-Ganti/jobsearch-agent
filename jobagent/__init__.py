"""jobagent — a personal, low-cost daily job-hunting pipeline."""

from .models import JobPosting, RawPosting
from .pipeline import Pipeline, Stage

__version__ = "0.1.0"
__all__ = ["JobPosting", "Pipeline", "RawPosting", "Stage"]

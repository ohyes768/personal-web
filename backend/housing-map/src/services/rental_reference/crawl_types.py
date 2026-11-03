"""Shared crawl types for every rental provider.

These types describe the crawl protocol (per-seed outcome, cancellation,
progress counters) and carry no provider-specific behavior, so they live
outside any provider module.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SeedRunResult:
    """Per-seed crawl outcome: one community seed with a completeness status.

    status is one of complete / truncated / list_failed / partial_detail /
    empty_ok (empty listing page = success with zero samples). Samples of
    failed seeds are kept for diagnostics only; callers must not publish them.
    """
    seed: str
    samples: list[dict] = field(default_factory=list)
    pages_fetched: int = 0
    pages_truncated: bool = False
    detail_success: int = 0
    detail_failed: int = 0
    duplicate_ids: int = 0
    status: str = 'complete'
    errors: list[dict] = field(default_factory=list)
    detail_cache_hits: int = 0
    deferred: bool = False
    pause_reason: str | None = None


class RentalCrawlCancelled(Exception):
    """cancel_event fired mid-crawl; completed and partial work stays usable for reporting."""

    def __init__(self, completed: list[SeedRunResult], partial: SeedRunResult | None):
        super().__init__('rental crawl cancelled')
        self.completed = completed
        self.partial = partial


class CrawlProgress:
    """Read-only counters for a running crawl; page/detail counts are auxiliary, never a percent."""

    def __init__(self, total_seeds: int):
        self.total_seeds = total_seeds
        self.processed_seeds = 0
        self.current_seed: str | None = None
        self.pages_fetched = 0
        self.details_fetched = 0

    def snapshot(self) -> dict:
        return {'total_seeds': self.total_seeds, 'processed_seeds': self.processed_seeds,
                'current_seed': self.current_seed, 'pages_fetched': self.pages_fetched,
                'details_fetched': self.details_fetched}

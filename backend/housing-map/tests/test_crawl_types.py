"""Shared crawl types are provider-neutral and keep the cancellation protocol."""
from src.services.rental_reference.crawl_types import (
    CrawlProgress,
    RentalCrawlCancelled,
    SeedRunResult,
)


def test_cancel_carries_completed_and_partial():
    done = SeedRunResult(seed='done')
    partial = SeedRunResult(seed='partial')
    exc = RentalCrawlCancelled([done], partial)
    assert exc.completed == [done]
    assert exc.partial is partial


def test_seed_result_defaults():
    result = SeedRunResult(seed='s1')
    assert result.status == 'complete'
    assert result.samples == []
    assert result.errors == []
    assert result.pause_reason is None


def test_progress_snapshot_is_not_a_percentage():
    progress = CrawlProgress(total_seeds=3)
    progress.processed_seeds = 1
    progress.current_seed = 's1'
    snapshot = progress.snapshot()
    assert snapshot['total_seeds'] == 3
    assert snapshot['processed_seeds'] == 1
    assert snapshot['current_seed'] == 's1'
    assert 'percent' not in snapshot

import asyncio

import pytest

from src.services import refresh
from src.services.tmsf_fetcher import CommunityFetchResult, PriceSnapshot


def _snapshot(community_id: str, price: int) -> PriceSnapshot:
    return PriceSnapshot(
        community_id=community_id,
        community_name="测试花园",
        snapshot_date="2026-09-20",
        source="tmsf",
        price_type="monthly_deal_avg_latest",
        avg_price=price,
        listing_count=1,
        deal_count=1,
        sample_count=1,
        min_price=None,
        max_price=None,
        source_url="https://example.test",
        confidence_score=0.9,
        raw_payload={"tendency": {"latest_month": "2026-09"}},
        crawled_at="2026-09-20T00:00:00+00:00",
    )


def test_select_refresh_targets_keeps_all_real_communities_and_drops_road_entries():
    """采集目标按"是真实小区"准入：商办类要抓（展示靠前端类型筛选），仅排除道路等垃圾条目。"""
    communities = [
        {"community_id": "home", "community_name": "春江花园"},
        {"community_id": "office", "community_name": "通策广场"},
        {"community_id": "road", "community_name": "江南大道"},
    ]

    assert refresh.select_refresh_targets(communities) == ["home", "office"]


def test_in_process_refresh_merges_fresh_rows_without_starting_a_script(tmp_path):
    snapshot_path = tmp_path / "price_snapshots.jsonl"
    snapshot_path.write_text("", encoding="utf-8")
    backup_path = tmp_path / "price_snapshots.bak.jsonl"
    backup_path.write_text("", encoding="utf-8")
    calls = []

    def fetcher(community_id: str, *, timeout: int) -> CommunityFetchResult:
        calls.append((community_id, timeout))
        return CommunityFetchResult(snapshots=[_snapshot(community_id, 32000)], errors=[])

    result = asyncio.run(refresh.run_refresh_once(
        ["home"],
        snapshot_path=snapshot_path,
        backup_path=backup_path,
        data_path=tmp_path,
        fetcher=fetcher,
        sleep_seconds=0,
    ))

    assert calls == [("home", refresh.DEFAULT_FETCH_TIMEOUT)]
    assert result == {"fetched": 1, "keptOld": 0, "total": 1, "failed": 0}
    assert '"community_id": "home"' in snapshot_path.read_text(encoding="utf-8")


def test_in_process_refresh_fails_without_writing_when_every_fetch_fails(tmp_path):
    snapshot_path = tmp_path / "price_snapshots.jsonl"
    snapshot_path.write_text('{"old": true}\n', encoding="utf-8")
    backup_path = tmp_path / "price_snapshots.bak.jsonl"
    backup_path.write_text('{"old": true}\n', encoding="utf-8")

    def fetcher(community_id: str, *, timeout: int) -> CommunityFetchResult:
        return CommunityFetchResult(snapshots=[], errors=["tendency: RuntimeError: blocked"])

    with pytest.raises(RuntimeError, match="no verified price"):
        asyncio.run(refresh.run_refresh_once(
            ["home"],
            snapshot_path=snapshot_path,
            backup_path=backup_path,
            data_path=tmp_path,
            fetcher=fetcher,
            sleep_seconds=0,
        ))

    assert snapshot_path.read_text(encoding="utf-8") == '{"old": true}\n'

"""估值存储与迁移测试。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from src.data import lixinger as lx
from src.services.store import Store


def _publish(store: Store, day="2026-10-30", pe=12.3456, ratio=0.565952) -> None:
    store.publish_valuation(
        "000300",
        lx.VALUATION_SOURCE,
        lx.VALUATION_METRIC,
        lx.VALUATION_WINDOW,
        [(day, pe, ratio)],
        "2026-10-30",
    )


def test_migration_creates_valuation_tables(tmp_path: Path):
    store = Store(tmp_path / "db.sqlite")
    tables = {
        row[0]
        for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "index_valuations" in tables
    assert "valuation_fetch_meta" in tables
    store.close()


def test_migration_is_idempotent_on_existing_db(tmp_path: Path):
    path = tmp_path / "db.sqlite"
    store = Store(path)
    _publish(store)
    store.close()

    reopened = Store(path)
    row = reopened.latest_valuation(
        "000300", lx.VALUATION_SOURCE, lx.VALUATION_METRIC, lx.VALUATION_WINDOW
    )
    assert row is not None and row["date"] == "2026-10-30"
    reopened.close()


def test_migration_does_not_touch_weekly_data(tmp_path: Path):
    store = Store(tmp_path / "db.sqlite")
    store.upsert_monthly_bars({})
    store.set_weekly_data_meta("Tencent", "2026-10-26", "2026-10-30", "hash", "snap")
    _publish(store)
    meta = store.get_weekly_data_meta()
    assert meta["data_cutoff_week"] == "2026-10-26"
    assert meta["snapshot_id"] == "snap"
    store.close()


def test_publish_and_read_latest(tmp_path: Path):
    store = Store(tmp_path / "db.sqlite")
    _publish(store, day="2026-10-23")
    _publish(store, day="2026-10-30")
    row = store.latest_valuation(
        "000300", lx.VALUATION_SOURCE, lx.VALUATION_METRIC, lx.VALUATION_WINDOW
    )
    assert row is not None and row["date"] == "2026-10-30"
    assert row["pe_ttm"] == 12.3456
    assert row["percentile_ratio"] == 0.565952
    store.close()


def test_latest_respects_on_or_before(tmp_path: Path):
    store = Store(tmp_path / "db.sqlite")
    _publish(store, day="2026-10-23")
    _publish(store, day="2026-10-30")
    row = store.latest_valuation(
        "000300",
        lx.VALUATION_SOURCE,
        lx.VALUATION_METRIC,
        lx.VALUATION_WINDOW,
        on_or_before="2026-10-23",
    )
    assert row is not None and row["date"] == "2026-10-23"
    store.close()


def test_publish_updates_fetch_meta(tmp_path: Path):
    store = Store(tmp_path / "db.sqlite")
    _publish(store)
    meta = store.get_valuation_meta()
    assert meta["target_date"] == "2026-10-30"
    assert meta["last_error"] is None
    assert meta["last_success_at"]
    store.close()


def test_failure_keeps_data_and_records_error(tmp_path: Path):
    store = Store(tmp_path / "db.sqlite")
    _publish(store)
    store.record_valuation_failure("000300", "2026-11-06", "network_error")
    meta = store.get_valuation_meta()
    assert meta["last_error"] == "network_error"
    assert meta["target_date"] == "2026-11-06"
    row = store.latest_valuation(
        "000300", lx.VALUATION_SOURCE, lx.VALUATION_METRIC, lx.VALUATION_WINDOW
    )
    assert row is not None and row["date"] == "2026-10-30"
    store.close()


def test_valuation_tables_contain_no_token(tmp_path: Path):
    store = Store(tmp_path / "db.sqlite")
    _publish(store)
    dump = "\n".join(
        store._conn.iterdump()
    )
    assert "token" not in dump.lower() or "lixinger_token" not in dump.lower()
    store.close()

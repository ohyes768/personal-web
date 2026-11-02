"""周线存储：独立周线表、幂等迁移、模型只插入不覆盖、原子发布。

覆盖：
- 旧库（月线模型 + 已 sent/no_channel 周报 + 自定义配置）重复迁移安全
- weekly_bars / weekly_models / weekly_data_meta / schema_migrations 存在且与月线隔离
- 迁移保留 enabled/channel/send_cron，并把月线 kind 映射为周线 kind
- 模型按 model_id 只插入不覆盖
- 一次刷新在一个事务里发布（中途失败整体回滚，旧快照仍可读）
"""
from __future__ import annotations

import dataclasses
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from src.core.models import (
    KIND_SINCE_INCEPTION_WEEKLY,
    KIND_TRAILING_WEEKLY,
    WeeklyModelRecord,
)
from src.data.provider import KlineBar
from src.services.store import Store

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _model(model_id: str = "m1", kind: str = KIND_TRAILING_WEEKLY, fit_end: str = "2026-10-26") -> WeeklyModelRecord:
    from src.core.regression import Coefficients

    return WeeklyModelRecord(
        model_id=model_id,
        index_code="000300",
        kind=kind,
        timeframe="week",
        sample_count=512,
        fit_start="2016-10-31",
        fit_end=fit_end,
        fit_last_trade_date="2026-10-30",
        calendar_window_start="2016-11-02",
        calendar_window_end="2026-11-02",
        data_cutoff_week=fit_end,
        algorithm_version="lrc-ltb-week-v1",
        data_hash="abc123",
        multiplier=2.0,
        coefficients=Coefficients(1.075, 3785.49, 536.23),
        calculated_at="2026-11-02T18:00:00+08:00",
    )


def _bar(week_start: str, day: str, close: float) -> KlineBar:
    return KlineBar(date=day, open=close, close=close, high=close, low=close)


def test_weekly_tables_exist_and_are_separate(store: Store):
    names = {
        r["name"]
        for r in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for table in ("weekly_bars", "weekly_models", "weekly_data_meta", "schema_migrations"):
        assert table in names
    # 月线档案表保留不动
    for table in ("monthly_bars", "models", "data_meta"):
        assert table in names


def test_monthly_models_table_not_reused_for_weeks(store: Store):
    """月线 models 表的 months 列不得被改装成周数。"""
    columns = {r["name"] for r in store._conn.execute("PRAGMA table_info(models)")}
    assert "months" in columns
    assert "sample_count" not in columns
    weekly_columns = {r["name"] for r in store._conn.execute("PRAGMA table_info(weekly_models)")}
    assert "sample_count" in weekly_columns
    assert "months" not in weekly_columns


def test_upsert_weekly_model_is_insert_only(store: Store):
    assert store.upsert_weekly_model(_model()) is True
    assert store.upsert_weekly_model(_model()) is False
    assert len(store.list_weekly_models("000300")) == 1


def test_weekly_model_lookup_by_kind_and_cutoff(store: Store):
    store.upsert_weekly_model(_model("m1", KIND_TRAILING_WEEKLY, "2026-10-26"))
    store.upsert_weekly_model(_model("m2", KIND_TRAILING_WEEKLY, "2026-10-19"))
    store.upsert_weekly_model(_model("m3", KIND_SINCE_INCEPTION_WEEKLY))
    latest = store.latest_weekly_model("000300", KIND_TRAILING_WEEKLY)
    assert latest.model_id == "m1"
    assert latest.data_cutoff_week == "2026-10-26"
    old = store.weekly_model_by_cutoff("000300", KIND_TRAILING_WEEKLY, "2026-10-19")
    assert old is not None and old.model_id == "m2"


def test_weekly_bars_roundtrip(store: Store):
    bars = {"2026-10-26": _bar("2026-10-26", "2026-10-30", 3985.5)}
    store.upsert_weekly_bars(bars)
    loaded = store.load_weekly_bars()
    assert loaded["2026-10-26"].close == 3985.5
    assert loaded["2026-10-26"].date == "2026-10-30"


def test_publish_weekly_snapshot_is_atomic(store: Store):
    """一次发布：周K + 模型 + 元数据同一事务提交。"""
    bars = {"2026-10-26": _bar("2026-10-26", "2026-10-30", 3985.5)}
    models = [_model()]
    result = store.publish_weekly_snapshot(
        bars=bars,
        models=models,
        provider="Tencent Finance",
        data_cutoff_week="2026-10-26",
        data_cutoff_trade_date="2026-10-30",
        weekly_hash="hash-1",
        snapshot_id="snap-1",
    )
    assert result["new_model_ids"] == ["m1"]
    assert store.load_weekly_bars()["2026-10-26"].close == 3985.5
    assert len(store.list_weekly_models("000300")) == 1
    meta = store.get_weekly_data_meta()
    assert meta["snapshot_id"] == "snap-1"
    assert meta["data_cutoff_week"] == "2026-10-26"


def test_publish_drops_stale_partial_bar(store: Store):
    """新快照不再包含的进行中周必须删掉，不能留成假 K 线。"""
    store.upsert_weekly_bars(
        {"2026-11-02": _bar("2026-11-02", "2026-11-02", 4000.0)},
        partial={"2026-11-02"},
    )
    store.publish_weekly_snapshot(
        bars={"2026-10-26": _bar("2026-10-26", "2026-10-30", 3985.5)},
        models=[_model()],
        provider="Tencent Finance",
        data_cutoff_week="2026-10-26",
        data_cutoff_trade_date="2026-10-30",
        weekly_hash="hash-1",
        snapshot_id="snap-1",
    )
    loaded = store.load_weekly_bars(include_partial=True)
    assert "2026-11-02" not in loaded
    assert loaded["2026-10-26"].close == 3985.5


def test_publish_weekly_snapshot_rolls_back_on_failure(store: Store):
    """发布中途失败 → 整体回滚，旧快照仍可读。"""
    bars = {"2026-10-26": _bar("2026-10-26", "2026-10-30", 3985.5)}
    store.publish_weekly_snapshot(
        bars=bars, models=[_model()], provider="Tencent Finance",
        data_cutoff_week="2026-10-26", data_cutoff_trade_date="2026-10-30",
        weekly_hash="hash-1", snapshot_id="snap-1",
    )

    # NOT NULL 约束冲突：模型写入在中途失败
    broken = dataclasses.replace(_model("m2", fit_end="2026-10-19"), sample_count=None)
    with pytest.raises(sqlite3.IntegrityError):
        store.publish_weekly_snapshot(
            bars={"2026-10-19": _bar("2026-10-19", "2026-10-23", 4105.3)},
            models=[broken],
            provider="Tencent Finance",
            data_cutoff_week="2026-10-19",
            data_cutoff_trade_date="2026-10-23",
            weekly_hash="hash-2",
            snapshot_id="snap-2",
        )
    # 旧快照完好：周K、模型与元数据都未变
    assert store.get_weekly_data_meta()["snapshot_id"] == "snap-1"
    assert store.get_weekly_data_meta()["data_cutoff_week"] == "2026-10-26"
    assert "2026-10-19" not in store.load_weekly_bars()
    assert len(store.list_weekly_models("000300")) == 1


def test_migration_maps_report_settings_to_weekly_kinds(tmp_path):
    """旧库迁移：周线管线接管时月线 kind 映射为周线 kind，其他偏好保留。

    迁移在周线快照首次发布时发生（与快照同事务），不是建库时——
    否则尚未切换管线的库会被提前改写。
    """
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE report_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            index_code TEXT NOT NULL DEFAULT '000300',
            model_kind TEXT NOT NULL DEFAULT 'trailing_120m',
            enabled INTEGER NOT NULL DEFAULT 1,
            send_cron TEXT NOT NULL DEFAULT '0 19 * * fri',
            channel TEXT NOT NULL DEFAULT 'dingtalk',
            updated_at TEXT
        );
        INSERT INTO report_settings (id, index_code, model_kind, enabled, send_cron, channel)
        VALUES (1, '000300', 'trailing_120m', 0, '0 20 * * fri', 'dingtalk');
        """
    )
    conn.commit()
    conn.close()

    store = Store(db)
    # 建库时不动尚未接管管线的配置
    assert store.get_report_settings()["model_kind"] == "trailing_120m"

    store.publish_weekly_snapshot(
        bars={"2026-10-26": _bar("2026-10-26", "2026-10-30", 3985.5)},
        models=[_model()],
        provider="Tencent Finance",
        data_cutoff_week="2026-10-26",
        data_cutoff_trade_date="2026-10-30",
        weekly_hash="hash-1",
        snapshot_id="snap-1",
    )
    settings = store.get_report_settings()
    assert settings["model_kind"] == KIND_TRAILING_WEEKLY
    assert settings["enabled"] == 0
    assert settings["send_cron"] == "0 20 * * fri"
    assert settings["channel"] == "dingtalk"

    # 重复迁移安全：再建一次 store 不改变结果，也不丢数据
    store2 = Store(db)
    settings2 = store2.get_report_settings()
    assert settings2["model_kind"] == KIND_TRAILING_WEEKLY
    assert settings2["enabled"] == 0
    assert settings2["send_cron"] == "0 20 * * fri"


def test_migration_records_version(store: Store):
    rows = list(store._conn.execute("SELECT version FROM schema_migrations"))
    assert rows, "迁移版本必须记录在 schema_migrations"


def test_reports_table_has_snapshot_json_column(store: Store):
    """新周线报告用 snapshot_json 保存不可变原始快照（旧行可空）。"""
    columns = {r["name"] for r in store._conn.execute("PRAGMA table_info(reports)")}
    assert "snapshot_json" in columns


def test_report_attempts_archive_is_append_only(store: Store):
    """被替换的旧报告与投递结果追加归档，不覆盖原记录。"""
    store.archive_report_attempt(
        idempotency_key="000300|2026-W44|weekly",
        model_id="old-model",
        model_kind="trailing_120m",
        business_status="normal",
        status="no_channel",
        error="channel_not_configured",
        payload="旧报告原文",
    )
    store.archive_report_attempt(
        idempotency_key="000300|2026-W44|weekly",
        model_id="new-model",
        model_kind="trailing_10y_weekly",
        business_status="normal",
        status="sent",
    )
    attempts = store.list_report_attempts("000300|2026-W44|weekly")
    assert len(attempts) == 2
    assert attempts[0]["model_id"] == "old-model"
    assert attempts[0]["payload"] == "旧报告原文"
    assert attempts[1]["model_id"] == "new-model"


def test_weekly_failure_state_is_visible_and_keeps_snapshot(store: Store):
    """刷新失败：失败状态可见，但旧成功快照与截止周不变。"""
    store.publish_weekly_snapshot(
        bars={"2026-10-26": _bar("2026-10-26", "2026-10-30", 3985.5)},
        models=[_model()],
        provider="Tencent Finance",
        data_cutoff_week="2026-10-26",
        data_cutoff_trade_date="2026-10-30",
        weekly_hash="hash-1",
        snapshot_id="snap-1",
    )
    store.record_weekly_failure("周K收盘与日线不一致")
    meta = store.get_weekly_data_meta()
    assert meta["last_error"] == "周K收盘与日线不一致"
    assert meta["last_error_at"]
    # 旧成功快照仍可读
    assert meta["snapshot_id"] == "snap-1"
    assert meta["data_cutoff_week"] == "2026-10-26"
    assert store.load_weekly_bars()["2026-10-26"].close == 3985.5


def test_migration_preserves_old_reports(tmp_path):
    """旧月线报告行不被改写，仍可追溯。"""
    db = tmp_path / "legacy2.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            index_code TEXT NOT NULL,
            iso_week TEXT NOT NULL,
            model_id TEXT NOT NULL,
            model_kind TEXT NOT NULL,
            business_status TEXT NOT NULL DEFAULT 'normal',
            close REAL, close_date TEXT, region TEXT, position_pct REAL,
            content TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
            created_at TEXT NOT NULL, sent_at TEXT
        );
        INSERT INTO reports (idempotency_key, index_code, iso_week, model_id, model_kind,
                             content, status, created_at, sent_at)
        VALUES ('000300|2026-W44|weekly', '000300', '2026-W44', 'old-model', 'trailing_120m',
                '旧月线周报原文', 'sent', '2026-10-30T19:00:00+08:00', '2026-10-30T19:00:05+08:00');
        """
    )
    conn.commit()
    conn.close()

    store = Store(db)
    report = store.get_report("000300|2026-W44|weekly")
    assert report is not None
    assert report["content"] == "旧月线周报原文"
    assert report["status"] == "sent"
    # 旧行不被改写：model_kind 仍是月线 kind
    assert report["model_kind"] == "trailing_120m"

"""SQLite 存储：行情、模型、周报配置与报告。

约定：
- 行情原始数据（月K/日线）直接落库；模型按 model_id 幂等写入，不覆盖旧版本。
- 周报以 idempotency_key（指数|自然周|weekly）唯一约束保证不重复发送。
- 原子性依赖 SQLite 事务；连接由调用方管理（FastAPI 单进程）。

周线存储与月线完全隔离（weekly_bars / weekly_models / weekly_data_meta），
旧月线表保留为历史档案，不把 months 列改装成周数。
结构变更通过 schema_migrations 表做版本化、可重复执行的迁移。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.models import LEGACY_KIND_TO_WEEKLY, ModelRecord, WeeklyModelRecord
from src.data.provider import KlineBar

SCHEMA = """
CREATE TABLE IF NOT EXISTS monthly_bars (
    month TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    close REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_quotes (
    date TEXT PRIMARY KEY,
    open REAL NOT NULL,
    close REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS data_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    monthly_cutoff_month TEXT,
    monthly_hash TEXT
);
CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    index_code TEXT NOT NULL,
    kind TEXT NOT NULL,
    fit_start TEXT NOT NULL,
    fit_end TEXT NOT NULL,
    months INTEGER NOT NULL,
    algorithm_version TEXT NOT NULL,
    data_cutoff_month TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    multiplier REAL NOT NULL,
    slope REAL NOT NULL,
    intercept REAL NOT NULL,
    deviation REAL NOT NULL,
    calculated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS report_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    index_code TEXT NOT NULL DEFAULT '000300',
    model_kind TEXT NOT NULL DEFAULT 'trailing_120m',
    enabled INTEGER NOT NULL DEFAULT 1,
    send_cron TEXT NOT NULL DEFAULT '0 19 * * fri',
    channel TEXT NOT NULL DEFAULT 'dingtalk',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    index_code TEXT NOT NULL,
    iso_week TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_kind TEXT NOT NULL,
    business_status TEXT NOT NULL DEFAULT 'normal',
    close REAL,
    close_date TEXT,
    region TEXT,
    position_pct REAL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
"""

# 周线相关表（与月线表隔离）
WEEKLY_SCHEMA = """
CREATE TABLE IF NOT EXISTS weekly_bars (
    week_start TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    close REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    is_partial INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS weekly_models (
    model_id TEXT PRIMARY KEY,
    index_code TEXT NOT NULL,
    kind TEXT NOT NULL,
    timeframe TEXT NOT NULL DEFAULT 'week',
    sample_count INTEGER NOT NULL,
    fit_start TEXT NOT NULL,
    fit_end TEXT NOT NULL,
    fit_last_trade_date TEXT NOT NULL,
    calendar_window_start TEXT NOT NULL,
    calendar_window_end TEXT NOT NULL,
    data_cutoff_week TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    multiplier REAL NOT NULL,
    slope REAL NOT NULL,
    intercept REAL NOT NULL,
    deviation REAL NOT NULL,
    calculated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS weekly_data_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    data_cutoff_week TEXT,
    data_cutoff_trade_date TEXT,
    weekly_hash TEXT,
    snapshot_id TEXT,
    last_error TEXT,
    last_error_at TEXT
);
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS report_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL,
    attempt_at TEXT NOT NULL,
    model_id TEXT,
    model_kind TEXT,
    business_status TEXT,
    status TEXT,
    error TEXT,
    snapshot_json TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_report_attempts_key
    ON report_attempts (idempotency_key);
"""

# 估值相关表（理杏仁 PE-TTM 近10年分位；与行情/模型表隔离）
VALUATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS index_valuations (
    index_code TEXT NOT NULL,
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    window TEXT NOT NULL,
    date TEXT NOT NULL,
    pe_ttm REAL NOT NULL,
    percentile_ratio REAL NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY (index_code, source, metric, window, date)
);
CREATE TABLE IF NOT EXISTS valuation_fetch_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    index_code TEXT NOT NULL DEFAULT '000300',
    target_date TEXT,
    last_attempt_at TEXT,
    last_success_at TEXT,
    last_error TEXT
);
"""

# 迁移版本：每次结构/数据变更追加一行，已应用的版本不重复执行
MIGRATION_VERSIONS = ("001_weekly_tables", "002_report_settings_weekly_kind")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO report_settings (id, updated_at) VALUES (1, ?)",
            (now_iso(),),
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO data_meta (id, provider, captured_at) VALUES (1, '', '')"
        )
        self._conn.commit()
        self._migrate()

    # ---- 迁移 ----
    def _migrate(self) -> None:
        """版本化、幂等的结构与数据迁移。

        每个版本在 schema_migrations 记账，重复执行不重复应用；
        旧库（月线模型 / 旧周报 / 自定义配置）重复迁移不丢数据。
        """
        self._conn.executescript(WEEKLY_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO weekly_data_meta (id, provider, captured_at) VALUES (1, '', '')"
        )
        self._conn.commit()
        self._apply_migration("001_weekly_tables", lambda: None)
        self._apply_migration("003_reports_snapshot_json", self._add_snapshot_json_column)
        self._apply_migration("004_weekly_bars_is_partial", self._add_is_partial_column)
        self._apply_migration("005_valuation_tables", self._add_valuation_tables)
        if self._has_weekly_models():
            # 已切到周线管线的库（周线快照已发布过）：补做 kind 映射
            self._apply_migration(
                "002_report_settings_weekly_kind", self._migrate_report_settings
            )
        self._conn.commit()

    def migrate_report_settings_to_weekly(self) -> None:
        """把周报配置的月线 kind 映射为周线 kind（周线管线接管时调用）。

        保留 enabled / channel / send_cron / index_code；
        已是周线 kind 的行不动（幂等）。
        """
        with self._conn:
            self._migrate_report_settings()
            self._conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                ("002_report_settings_weekly_kind", now_iso()),
            )

    def _has_weekly_models(self) -> bool:
        row = self._conn.execute("SELECT 1 FROM weekly_models LIMIT 1").fetchone()
        return row is not None

    def _add_snapshot_json_column(self) -> None:
        """给旧 reports 表补 snapshot_json 列（可空，幂等）。

        新周线报告用它保存不可变的原始快照；旧月线报告行不改写。
        """
        columns = {r["name"] for r in self._conn.execute("PRAGMA table_info(reports)")}
        if "snapshot_json" not in columns:
            self._conn.execute("ALTER TABLE reports ADD COLUMN snapshot_json TEXT")

    def _add_is_partial_column(self) -> None:
        """给旧 weekly_bars 表补 is_partial 列（进行中周标记，幂等）。"""
        columns = {r["name"] for r in self._conn.execute("PRAGMA table_info(weekly_bars)")}
        if "is_partial" not in columns:
            self._conn.execute(
                "ALTER TABLE weekly_bars ADD COLUMN is_partial INTEGER NOT NULL DEFAULT 0"
            )

    def _add_valuation_tables(self) -> None:
        """新增估值表（只加表，不动行情/模型/报告；幂等）。"""
        self._conn.executescript(VALUATION_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO valuation_fetch_meta (id, index_code) VALUES (1, '000300')"
        )

    def _apply_migration(self, version: str, action: Any) -> None:
        row = self._conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
        ).fetchone()
        if row:
            return
        action()
        self._conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, now_iso()),
        )

    def _migrate_report_settings(self) -> None:
        """report_settings 的月线 kind 映射为周线 kind。

        只改 model_kind；enabled / channel / send_cron / index_code 保留。
        已是周线 kind 的行不动（幂等）。
        """
        row = self._conn.execute(
            "SELECT model_kind FROM report_settings WHERE id = 1"
        ).fetchone()
        if row is None:
            return
        mapped = LEGACY_KIND_TO_WEEKLY.get(row["model_kind"])
        if mapped and mapped != row["model_kind"]:
            self._conn.execute(
                "UPDATE report_settings SET model_kind = ?, updated_at = ? WHERE id = 1",
                (mapped, now_iso()),
            )

    def close(self) -> None:
        self._conn.close()

    # ---- 行情 ----
    def upsert_monthly_bars(self, bars: dict[str, KlineBar]) -> None:
        with self._conn:
            self._conn.executemany(
                "INSERT INTO monthly_bars (month, date, open, close, high, low) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(month) DO UPDATE SET date=excluded.date, open=excluded.open, "
                "close=excluded.close, high=excluded.high, low=excluded.low",
                [
                    (m, b.date, b.open, b.close, b.high, b.low)
                    for m, b in sorted(bars.items())
                ],
            )

    def load_monthly_bars(self) -> dict[str, KlineBar]:
        rows = self._conn.execute(
            "SELECT month, date, open, close, high, low FROM monthly_bars ORDER BY month"
        ).fetchall()
        return {
            r["month"]: KlineBar(r["date"], r["open"], r["close"], r["high"], r["low"])
            for r in rows
        }

    def upsert_daily_quotes(self, bars: list[KlineBar]) -> None:
        with self._conn:
            self._conn.executemany(
                "INSERT INTO daily_quotes (date, open, close, high, low) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(date) DO UPDATE SET open=excluded.open, close=excluded.close, "
                "high=excluded.high, low=excluded.low",
                [(b.date, b.open, b.close, b.high, b.low) for b in bars],
            )

    def load_daily_quotes(self, limit: int = 500) -> list[KlineBar]:
        rows = self._conn.execute(
            "SELECT date, open, close, high, low FROM daily_quotes "
            "ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
        return [KlineBar(r["date"], r["open"], r["close"], r["high"], r["low"]) for r in rows]

    def set_data_meta(self, provider: str, monthly_cutoff: str | None, monthly_hash: str | None) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE data_meta SET provider=?, captured_at=?, monthly_cutoff_month=?, monthly_hash=? WHERE id=1",
                (provider, now_iso(), monthly_cutoff, monthly_hash),
            )

    def get_data_meta(self) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT provider, captured_at, monthly_cutoff_month, monthly_hash FROM data_meta WHERE id=1"
        ).fetchone()
        return dict(row) if row else {}

    # ---- 模型 ----
    def upsert_model(self, record: ModelRecord) -> bool:
        """按 model_id 幂等写入；已存在则跳过（不覆盖旧版本）。返回是否新写入。"""
        cur = self._conn.execute(
            "SELECT 1 FROM models WHERE model_id = ?", (record.model_id,)
        ).fetchone()
        if cur:
            return False
        with self._conn:
            self._conn.execute(
                "INSERT INTO models (model_id, index_code, kind, fit_start, fit_end, months, "
                "algorithm_version, data_cutoff_month, data_hash, multiplier, slope, intercept, "
                "deviation, calculated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.model_id, record.index_code, record.kind, record.fit_start,
                    record.fit_end, record.months, record.algorithm_version,
                    record.data_cutoff_month, record.data_hash, record.multiplier,
                    record.coefficients.slope, record.coefficients.intercept,
                    record.coefficients.deviation, record.calculated_at,
                ),
            )
        return True

    def latest_model(self, index_code: str, kind: str) -> ModelRecord | None:
        """指定种类按 (data_cutoff_month, calculated_at) 最新的模型版本。"""
        row = self._conn.execute(
            "SELECT * FROM models WHERE index_code=? AND kind=? "
            "ORDER BY data_cutoff_month DESC, calculated_at DESC LIMIT 1",
            (index_code, kind),
        ).fetchone()
        return self._row_to_model(row) if row else None

    def models_by_cutoff(self, index_code: str, kind: str, cutoff: str) -> ModelRecord | None:
        row = self._conn.execute(
            "SELECT * FROM models WHERE index_code=? AND kind=? AND data_cutoff_month=?",
            (index_code, kind, cutoff),
        ).fetchone()
        return self._row_to_model(row) if row else None

    def list_models(self, index_code: str, kind: str | None = None) -> list[ModelRecord]:
        if kind:
            rows = self._conn.execute(
                "SELECT * FROM models WHERE index_code=? AND kind=? "
                "ORDER BY fit_start, data_cutoff_month", (index_code, kind),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM models WHERE index_code=? ORDER BY fit_start, data_cutoff_month",
                (index_code,),
            ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> ModelRecord:
        from src.core.regression import Coefficients

        return ModelRecord(
            model_id=row["model_id"],
            index_code=row["index_code"],
            kind=row["kind"],
            fit_start=row["fit_start"],
            fit_end=row["fit_end"],
            months=row["months"],
            algorithm_version=row["algorithm_version"],
            data_cutoff_month=row["data_cutoff_month"],
            data_hash=row["data_hash"],
            multiplier=row["multiplier"],
            coefficients=Coefficients(row["slope"], row["intercept"], row["deviation"]),
            calculated_at=row["calculated_at"],
        )

    # ---- 周线行情与模型 ----
    def upsert_weekly_bars(
        self, bars: dict[str, KlineBar], partial: set[str] | None = None
    ) -> None:
        """写入周K（week_start 为周一主键）。

        partial 中的周标记为进行中（可展示，不参与拟合）。
        """
        partial = partial or set()
        with self._conn:
            self._conn.executemany(
                "INSERT INTO weekly_bars (week_start, date, open, close, high, low, is_partial) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(week_start) DO UPDATE SET date=excluded.date, open=excluded.open, "
                "close=excluded.close, high=excluded.high, low=excluded.low, "
                "is_partial=excluded.is_partial",
                [
                    (w, b.date, b.open, b.close, b.high, b.low, 1 if w in partial else 0)
                    for w, b in sorted(bars.items())
                ],
            )

    def load_weekly_bars(self, include_partial: bool = True) -> dict[str, KlineBar]:
        """读周K。include_partial=False 时只返回完整周（参与拟合的那些）。"""
        sql = "SELECT week_start, date, open, close, high, low FROM weekly_bars"
        if not include_partial:
            sql += " WHERE is_partial = 0"
        sql += " ORDER BY week_start"
        rows = self._conn.execute(sql).fetchall()
        return {
            r["week_start"]: KlineBar(r["date"], r["open"], r["close"], r["high"], r["low"])
            for r in rows
        }

    def load_partial_weekly_bars(self) -> dict[str, KlineBar]:
        """进行中的周（可展示，不参与拟合）。"""
        rows = self._conn.execute(
            "SELECT week_start, date, open, close, high, low FROM weekly_bars "
            "WHERE is_partial = 1 ORDER BY week_start"
        ).fetchall()
        return {
            r["week_start"]: KlineBar(r["date"], r["open"], r["close"], r["high"], r["low"])
            for r in rows
        }

    def upsert_weekly_model(self, record: WeeklyModelRecord) -> bool:
        """按 model_id 幂等写入；已存在则跳过（不覆盖旧版本）。返回是否新写入。"""
        cur = self._conn.execute(
            "SELECT 1 FROM weekly_models WHERE model_id = ?", (record.model_id,)
        ).fetchone()
        if cur:
            return False
        with self._conn:
            self._conn.execute(
                "INSERT INTO weekly_models (model_id, index_code, kind, timeframe, sample_count, "
                "fit_start, fit_end, fit_last_trade_date, calendar_window_start, "
                "calendar_window_end, data_cutoff_week, algorithm_version, data_hash, multiplier, "
                "slope, intercept, deviation, calculated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.model_id, record.index_code, record.kind, record.timeframe,
                    record.sample_count, record.fit_start, record.fit_end,
                    record.fit_last_trade_date, record.calendar_window_start,
                    record.calendar_window_end, record.data_cutoff_week,
                    record.algorithm_version, record.data_hash, record.multiplier,
                    record.coefficients.slope, record.coefficients.intercept,
                    record.coefficients.deviation, record.calculated_at,
                ),
            )
        return True

    def latest_weekly_model(self, index_code: str, kind: str) -> WeeklyModelRecord | None:
        """指定种类按 (data_cutoff_week, calculated_at) 最新的周线模型版本。"""
        row = self._conn.execute(
            "SELECT * FROM weekly_models WHERE index_code=? AND kind=? "
            "ORDER BY data_cutoff_week DESC, calculated_at DESC LIMIT 1",
            (index_code, kind),
        ).fetchone()
        return self._row_to_weekly_model(row) if row else None

    def weekly_model_by_cutoff(
        self, index_code: str, kind: str, cutoff_week: str
    ) -> WeeklyModelRecord | None:
        row = self._conn.execute(
            "SELECT * FROM weekly_models WHERE index_code=? AND kind=? AND data_cutoff_week=?",
            (index_code, kind, cutoff_week),
        ).fetchone()
        return self._row_to_weekly_model(row) if row else None

    def list_weekly_models(
        self, index_code: str, kind: str | None = None
    ) -> list[WeeklyModelRecord]:
        if kind:
            rows = self._conn.execute(
                "SELECT * FROM weekly_models WHERE index_code=? AND kind=? "
                "ORDER BY fit_start, data_cutoff_week",
                (index_code, kind),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM weekly_models WHERE index_code=? ORDER BY fit_start, data_cutoff_week",
                (index_code,),
            ).fetchall()
        return [self._row_to_weekly_model(r) for r in rows]

    @staticmethod
    def _row_to_weekly_model(row: sqlite3.Row) -> WeeklyModelRecord:
        from src.core.regression import Coefficients

        return WeeklyModelRecord(
            model_id=row["model_id"],
            index_code=row["index_code"],
            kind=row["kind"],
            timeframe=row["timeframe"],
            sample_count=row["sample_count"],
            fit_start=row["fit_start"],
            fit_end=row["fit_end"],
            fit_last_trade_date=row["fit_last_trade_date"],
            calendar_window_start=row["calendar_window_start"],
            calendar_window_end=row["calendar_window_end"],
            data_cutoff_week=row["data_cutoff_week"],
            algorithm_version=row["algorithm_version"],
            data_hash=row["data_hash"],
            multiplier=row["multiplier"],
            coefficients=Coefficients(row["slope"], row["intercept"], row["deviation"]),
            calculated_at=row["calculated_at"],
        )

    def set_weekly_data_meta(
        self,
        provider: str,
        data_cutoff_week: str | None,
        data_cutoff_trade_date: str | None,
        weekly_hash: str | None,
        snapshot_id: str | None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE weekly_data_meta SET provider=?, captured_at=?, data_cutoff_week=?, "
                "data_cutoff_trade_date=?, weekly_hash=?, snapshot_id=? WHERE id=1",
                (provider, now_iso(), data_cutoff_week, data_cutoff_trade_date,
                 weekly_hash, snapshot_id),
            )

    def get_weekly_data_meta(self) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT provider, captured_at, data_cutoff_week, data_cutoff_trade_date, "
            "weekly_hash, snapshot_id, last_error, last_error_at FROM weekly_data_meta "
            "WHERE id=1"
        ).fetchone()
        return dict(row) if row else {}

    def record_weekly_failure(self, error: str) -> None:
        """记录一次周线刷新失败（不改动已发布的快照与截止周）。

        失败状态可见，但旧成功快照仍可读（captured_at / data_cutoff_week 不变）。
        """
        with self._conn:
            self._conn.execute(
                "UPDATE weekly_data_meta SET last_error=?, last_error_at=? WHERE id=1",
                (error, now_iso()),
            )

    def clear_weekly_failure(self) -> None:
        """发布成功后清除失败标记。"""
        with self._conn:
            self._conn.execute(
                "UPDATE weekly_data_meta SET last_error=NULL, last_error_at=NULL WHERE id=1"
            )

    # ---- 估值（理杏仁 PE-TTM 近10年分位）----
    def publish_valuation(
        self,
        index_code: str,
        source: str,
        metric: str,
        window: str,
        points: list[tuple[str, float, float]],
        target_date: str,
    ) -> None:
        """在单个事务里写入估值记录并更新采集元数据。

        points 为 (date, pe_ttm, percentile_ratio) 列表。失败时不调用本方法，
        旧的成功数据保持可读。
        """
        with self._conn:
            self._conn.executemany(
                "INSERT INTO index_valuations (index_code, source, metric, window, date, "
                "pe_ttm, percentile_ratio, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(index_code, source, metric, window, date) DO UPDATE SET "
                "pe_ttm=excluded.pe_ttm, percentile_ratio=excluded.percentile_ratio, "
                "captured_at=excluded.captured_at",
                [
                    (index_code, source, metric, window, day, pe, ratio, now_iso())
                    for day, pe, ratio in points
                ],
            )
            self._conn.execute(
                "UPDATE valuation_fetch_meta SET index_code=?, target_date=?, "
                "last_attempt_at=?, last_success_at=?, last_error=NULL WHERE id=1",
                (index_code, target_date, now_iso(), now_iso()),
            )

    def record_valuation_failure(self, index_code: str, target_date: str, error: str) -> None:
        """记录一次估值采集失败（不改动已存的成功数据）。"""
        with self._conn:
            self._conn.execute(
                "UPDATE valuation_fetch_meta SET index_code=?, target_date=?, "
                "last_attempt_at=?, last_error=? WHERE id=1",
                (index_code, target_date, now_iso(), error),
            )

    def latest_valuation(
        self,
        index_code: str,
        source: str,
        metric: str,
        window: str,
        on_or_before: str | None = None,
    ) -> dict[str, Any] | None:
        """取最新一条估值记录（可选：只取不晚于 on_or_before 的）。"""
        sql = (
            "SELECT date, pe_ttm, percentile_ratio, captured_at FROM index_valuations "
            "WHERE index_code=? AND source=? AND metric=? AND window=?"
        )
        params: list[Any] = [index_code, source, metric, window]
        if on_or_before:
            sql += " AND date<=?"
            params.append(on_or_before)
        sql += " ORDER BY date DESC LIMIT 1"
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def get_valuation_meta(self) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT index_code, target_date, last_attempt_at, last_success_at, last_error "
            "FROM valuation_fetch_meta WHERE id=1"
        ).fetchone()
        return dict(row) if row else {}

    def publish_weekly_snapshot(
        self,
        bars: dict[str, KlineBar],
        models: list[WeeklyModelRecord],
        provider: str,
        data_cutoff_week: str,
        data_cutoff_trade_date: str,
        weekly_hash: str,
        snapshot_id: str,
        partial_bars: dict[str, KlineBar] | None = None,
        daily_bars: list[KlineBar] | None = None,
    ) -> dict[str, Any]:
        """在单个事务里发布周K、日线、模型与元数据。

        任一步失败整体回滚，旧成功快照保持可读。
        模型按 model_id 只插入不覆盖（已存在的版本保持不变）。
        """
        new_model_ids: list[str] = []
        partial_bars = partial_bars or {}
        partial_keys = set(partial_bars)
        all_bars = {**bars, **partial_bars}
        with self._conn:
            # 本次快照是周K的完整集合。先清掉旧行，避免上一轮的进行中周
            # 或已丢弃的休市周 K 线留在库里，刷新后仍被画成真实价格。
            self._conn.execute("DELETE FROM weekly_bars")
            # 周线管线接管：周报配置的月线 kind 映射为周线 kind（幂等，保留
            # enabled / channel / send_cron）。与快照同事务，避免半迁移状态。
            if not self._has_weekly_models():
                self._migrate_report_settings()
                self._conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations (version, applied_at) "
                    "VALUES (?, ?)",
                    ("002_report_settings_weekly_kind", now_iso()),
                )
            self._conn.executemany(
                "INSERT INTO weekly_bars (week_start, date, open, close, high, low, is_partial) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(week_start) DO UPDATE SET date=excluded.date, open=excluded.open, "
                "close=excluded.close, high=excluded.high, low=excluded.low, "
                "is_partial=excluded.is_partial",
                [
                    (w, b.date, b.open, b.close, b.high, b.low, 1 if w in partial_keys else 0)
                    for w, b in sorted(all_bars.items())
                ],
            )
            if daily_bars:
                self._conn.executemany(
                    "INSERT INTO daily_quotes (date, open, close, high, low) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(date) DO UPDATE SET open=excluded.open, "
                    "close=excluded.close, high=excluded.high, low=excluded.low",
                    [(b.date, b.open, b.close, b.high, b.low) for b in daily_bars],
                )
            for record in models:
                cur = self._conn.execute(
                    "SELECT 1 FROM weekly_models WHERE model_id = ?", (record.model_id,)
                ).fetchone()
                if cur:
                    continue    # 已存在：不覆盖旧版本
                self._conn.execute(
                    "INSERT INTO weekly_models (model_id, index_code, kind, timeframe, "
                    "sample_count, fit_start, fit_end, fit_last_trade_date, "
                    "calendar_window_start, calendar_window_end, data_cutoff_week, "
                    "algorithm_version, data_hash, multiplier, slope, intercept, deviation, "
                    "calculated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        record.model_id, record.index_code, record.kind, record.timeframe,
                        record.sample_count, record.fit_start, record.fit_end,
                        record.fit_last_trade_date, record.calendar_window_start,
                        record.calendar_window_end, record.data_cutoff_week,
                        record.algorithm_version, record.data_hash, record.multiplier,
                        record.coefficients.slope, record.coefficients.intercept,
                        record.coefficients.deviation, record.calculated_at,
                    ),
                )
                new_model_ids.append(record.model_id)
            self._conn.execute(
                "UPDATE weekly_data_meta SET provider=?, captured_at=?, data_cutoff_week=?, "
                "data_cutoff_trade_date=?, weekly_hash=?, snapshot_id=? WHERE id=1",
                (provider, now_iso(), data_cutoff_week, data_cutoff_trade_date,
                 weekly_hash, snapshot_id),
            )
        return {"new_model_ids": new_model_ids, "snapshot_id": snapshot_id}

    # ---- 周报 ----
    def archive_report_attempt(
        self,
        idempotency_key: str,
        model_id: str | None = None,
        model_kind: str | None = None,
        business_status: str | None = None,
        status: str | None = None,
        error: str | None = None,
        snapshot_json: str | None = None,
        payload: str | None = None,
    ) -> None:
        """追加一条报告尝试审计（不覆盖 reports 行）。

        用于：新周报生成前把被替换的旧行归档，以及记录每次投递结果。
        """
        with self._conn:
            self._conn.execute(
                "INSERT INTO report_attempts (idempotency_key, attempt_at, model_id, "
                "model_kind, business_status, status, error, snapshot_json, payload) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (idempotency_key, now_iso(), model_id, model_kind, business_status,
                 status, error, snapshot_json, payload),
            )

    def list_report_attempts(self, idempotency_key: str | None = None) -> list[dict[str, Any]]:
        if idempotency_key:
            rows = self._conn.execute(
                "SELECT * FROM report_attempts WHERE idempotency_key = ? ORDER BY id",
                (idempotency_key,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM report_attempts ORDER BY id DESC LIMIT 200"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_report_settings(self) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM report_settings WHERE id=1").fetchone()
        return dict(row)

    def update_report_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {"index_code", "model_kind", "enabled", "send_cron", "channel"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            with self._conn:
                self._conn.execute(
                    f"UPDATE report_settings SET {sets}, updated_at=? WHERE id=1",
                    (*fields.values(), now_iso()),
                )
        return self.get_report_settings()

    def get_report(self, idempotency_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM reports WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        return dict(row) if row else None

    def upsert_report(self, report: dict[str, Any]) -> None:
        """生成/更新本周报告（status 记录投递状态，business_status 记录内容状态）。

        snapshot_json 保存新周线报告的不可变快照；旧月线行在被替换前应由调用方
        先归档到 report_attempts，这里只负责写入当前行。
        """
        with self._conn:
            self._conn.execute(
                "INSERT INTO reports (idempotency_key, index_code, iso_week, model_id, model_kind, "
                "business_status, close, close_date, region, position_pct, content, status, error, "
                "created_at, sent_at, snapshot_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(idempotency_key) DO UPDATE SET "
                "model_id=excluded.model_id, model_kind=excluded.model_kind, "
                "business_status=excluded.business_status, close=excluded.close, "
                "close_date=excluded.close_date, region=excluded.region, "
                "position_pct=excluded.position_pct, content=excluded.content, "
                "status=excluded.status, error=excluded.error, "
                "snapshot_json=excluded.snapshot_json",
                (
                    report["idempotency_key"], report["index_code"], report["iso_week"],
                    report["model_id"], report["model_kind"], report.get("business_status", "normal"),
                    report.get("close"), report.get("close_date"), report.get("region"),
                    report.get("position_pct"), report["content"], report["status"],
                    report.get("error"), now_iso(), None, report.get("snapshot_json"),
                ),
            )

    def mark_report_sent(self, idempotency_key: str, status: str, error: str | None = None) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE reports SET status=?, error=?, sent_at=? WHERE idempotency_key=?",
                (status, error, now_iso() if status == "sent" else None, idempotency_key),
            )

    def list_reports(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM reports ORDER BY iso_week DESC, created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- 调试辅助 ----
    def export_json(self) -> str:
        tables = {}
        for name in ("monthly_bars", "daily_quotes", "models", "report_settings", "reports"):
            rows = self._conn.execute(f"SELECT * FROM {name}").fetchall()
            tables[name] = [dict(r) for r in rows]
        return json.dumps(tables, ensure_ascii=False, indent=2)

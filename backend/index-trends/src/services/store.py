"""SQLite 存储：行情、模型、周报配置与报告。

约定：
- 行情原始数据（月K/日线）直接落库；模型按 model_id 幂等写入，不覆盖旧版本。
- 周报以 idempotency_key（指数|自然周|weekly）唯一约束保证不重复发送。
- 原子性依赖 SQLite 事务；连接由调用方管理（FastAPI 单进程）。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.models import ModelRecord
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

    # ---- 周报 ----
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
        """生成/更新本周报告（status 记录投递状态，business_status 记录内容状态）。"""
        with self._conn:
            self._conn.execute(
                "INSERT INTO reports (idempotency_key, index_code, iso_week, model_id, model_kind, "
                "business_status, close, close_date, region, position_pct, content, status, error, created_at, sent_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(idempotency_key) DO UPDATE SET "
                "model_id=excluded.model_id, model_kind=excluded.model_kind, "
                "business_status=excluded.business_status, close=excluded.close, "
                "close_date=excluded.close_date, region=excluded.region, "
                "position_pct=excluded.position_pct, content=excluded.content, "
                "status=excluded.status, error=excluded.error",
                (
                    report["idempotency_key"], report["index_code"], report["iso_week"],
                    report["model_id"], report["model_kind"], report.get("business_status", "normal"),
                    report.get("close"), report.get("close_date"), report.get("region"),
                    report.get("position_pct"), report["content"], report["status"],
                    report.get("error"), now_iso(), None,
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

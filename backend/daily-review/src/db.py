"""
SQLite 访问层（标准库 sqlite3，无 ORM）
表：records / reports / ingest_log
幂等去重关键唯一约束：records UNIQUE(machine, kind, external_id)、
reports UNIQUE(report_type, period_start)。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import get_db_path

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    machine TEXT NOT NULL,
    kind TEXT NOT NULL,            -- session | task_board | git_commit
    project TEXT DEFAULT '',
    external_id TEXT NOT NULL,
    session_id TEXT DEFAULT '',
    title TEXT DEFAULT '',
    summary_text TEXT DEFAULT '',
    started_at TEXT DEFAULT '',
    ended_at TEXT DEFAULT '',
    payload_json TEXT DEFAULT '{}',
    ingested_at TEXT NOT NULL,
    UNIQUE(machine, kind, external_id)
);
CREATE INDEX IF NOT EXISTS idx_records_started ON records(started_at);
CREATE INDEX IF NOT EXISTS idx_records_project ON records(project, started_at);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    report_type TEXT NOT NULL,     -- daily | weekly
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    generated_at TEXT,
    summary_md TEXT DEFAULT '',
    record_ids_json TEXT DEFAULT '[]',
    status TEXT NOT NULL,          -- pending | done | failed
    UNIQUE(report_type, period_start)
);

CREATE TABLE IF NOT EXISTS ingest_log (
    machine TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    received_at TEXT NOT NULL,
    record_count INTEGER DEFAULT 0,
    status TEXT NOT NULL           -- ok | failed
);
-- NAS sync 的处理游标：batch_id = 文件相对路径，同一文件成功处理过即不再解析
CREATE INDEX IF NOT EXISTS idx_ingest_log_file ON ingest_log(machine, batch_id);

-- LLM token 消耗日汇总（两机合并展示）；upsert 幂等，重跑覆盖
CREATE TABLE IF NOT EXISTS usage_daily (
    machine TEXT NOT NULL,
    date TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    calls INTEGER DEFAULT 0,
    cost REAL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(machine, date, provider, model)
);
CREATE INDEX IF NOT EXISTS idx_usage_date ON usage_daily(date, machine);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_conn() -> sqlite3.Connection:
    """线程本地连接；API 线程与 sync 调用各自持有。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def init_db() -> None:
    get_conn().executescript(SCHEMA)


def upsert_record(row: dict) -> bool:
    """按 UNIQUE(machine,kind,external_id) 幂等插入；冲突时更新内容字段。

    返回是否新插入（冲突更新返回 False）。冲突更新（而不是 IGNORE）让
    采集口径/项目名归一化等规则改进后，采集端重发同一条记录即可自愈。
    """
    exists = get_record_by_external(row["machine"], row["kind"], row["external_id"]) is not None
    cur = get_conn().execute(
        """
        INSERT INTO records
        (id, machine, kind, project, external_id, session_id, title,
         summary_text, started_at, ended_at, payload_json, ingested_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(machine, kind, external_id) DO UPDATE SET
            project=excluded.project,
            title=excluded.title,
            summary_text=excluded.summary_text,
            started_at=excluded.started_at,
            ended_at=excluded.ended_at,
            payload_json=excluded.payload_json,
            ingested_at=excluded.ingested_at
        """,
        (
            row["id"],
            row["machine"],
            row["kind"],
            row.get("project", ""),
            row["external_id"],
            row.get("session_id", ""),
            row.get("title", ""),
            row.get("summary_text", ""),
            row.get("started_at", ""),
            row.get("ended_at", ""),
            json.dumps(row.get("payload", {}), ensure_ascii=False),
            row.get("ingested_at", now_iso()),
        ),
    )
    get_conn().commit()
    return not exists


def get_record_by_external(machine: str, kind: str, external_id: str) -> sqlite3.Row | None:
    return get_conn().execute(
        "SELECT * FROM records WHERE machine=? AND kind=? AND external_id=?",
        (machine, kind, external_id),
    ).fetchone()


def file_already_done(machine: str, batch_id: str) -> bool:
    """NAS sync 游标：该文件（batch_id）是否已成功处理过。"""
    row = get_conn().execute(
        "SELECT 1 FROM ingest_log WHERE machine=? AND batch_id=? AND status='ok' LIMIT 1",
        (machine, batch_id),
    ).fetchone()
    return row is not None


def log_ingest(machine: str, batch_id: str, record_count: int, status: str) -> None:
    get_conn().execute(
        "INSERT INTO ingest_log (machine, batch_id, received_at, record_count, status) VALUES (?,?,?,?,?)",
        (machine, batch_id, now_iso(), record_count, status),
    )
    get_conn().commit()


def upsert_usage(rows: list[dict]) -> int:
    """批量 upsert usage_daily（幂等，重跑覆盖）。返回写入行数。"""
    conn = get_conn()
    n = 0
    for r in rows:
        conn.execute(
            """
            INSERT INTO usage_daily
            (machine, date, provider, model, input_tokens, output_tokens,
             cache_read_tokens, cache_write_tokens, reasoning_tokens, calls, cost, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(machine, date, provider, model)
            DO UPDATE SET input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
                          cache_read_tokens=excluded.cache_read_tokens,
                          cache_write_tokens=excluded.cache_write_tokens,
                          reasoning_tokens=excluded.reasoning_tokens,
                          calls=excluded.calls, cost=excluded.cost,
                          updated_at=excluded.updated_at
            """,
            (
                r["machine"], r["date"], r["provider"], r["model"],
                r.get("input_tokens", 0), r.get("output_tokens", 0),
                r.get("cache_read_tokens", 0), r.get("cache_write_tokens", 0),
                r.get("reasoning_tokens", 0), r.get("calls", 0), r.get("cost", 0.0),
                r.get("updated_at", now_iso()),
            ),
        )
        n += 1
    conn.commit()
    return n

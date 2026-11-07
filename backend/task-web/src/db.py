"""
SQLite 访问层（标准库 sqlite3，无 ORM）
表：tasks / task_schedules / runs / scheduler_heartbeat
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .config import get_db_path

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    command TEXT NOT NULL,
    cwd TEXT DEFAULT '',
    default_cron TEXT DEFAULT '',
    default_timeout INTEGER DEFAULT 600,
    engine TEXT DEFAULT 'shell',
    image TEXT,
    env_file TEXT,
    env TEXT,
    volumes TEXT
);

CREATE TABLE IF NOT EXISTS task_schedules (
    task_id TEXT PRIMARY KEY REFERENCES tasks(id),
    cron TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    timeout_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    scheduled_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    exit_code INTEGER,
    log_path TEXT,
    missed_schedule_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id, started_at);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

CREATE TABLE IF NOT EXISTS scheduler_heartbeat (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    updated_at TEXT NOT NULL
);
"""

RUN_ACTIVE_STATUSES = ("waiting", "running")


def get_conn() -> sqlite3.Connection:
    """线程本地连接；APScheduler 线程池与 API 线程各自持有。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        db_path: Path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        _local.conn = conn
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    # 旧卷无损升级：tasks 表补 docker 引擎列（2026-11-06 方案 B）
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    for name, ddl in (
        ("engine", "TEXT DEFAULT 'shell'"),
        ("image", "TEXT"),
        ("env_file", "TEXT"),
        ("env", "TEXT"),
        ("volumes", "TEXT"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {ddl}")
    conn.commit()


def now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_run_id(task_id: str) -> str:
    return f"{task_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os_unique()}"


def os_unique() -> str:
    import uuid

    return uuid.uuid4().hex[:6]


# ---------------------------------------------------------------------------
# tasks / schedules
# ---------------------------------------------------------------------------

def upsert_task(row: dict) -> None:
    get_conn().execute(
        """INSERT INTO tasks (id, name, description, command, cwd, default_cron, default_timeout,
             engine, image, env_file, env, volumes)
           VALUES (:id, :name, :description, :command, :cwd, :default_cron, :default_timeout,
             :engine, :image, :env_file, :env, :volumes)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name, description=excluded.description,
             command=excluded.command, cwd=excluded.cwd,
             default_cron=excluded.default_cron, default_timeout=excluded.default_timeout,
             engine=excluded.engine, image=excluded.image,
             env_file=excluded.env_file, env=excluded.env, volumes=excluded.volumes""",
        {
            "engine": "shell", "image": None, "env_file": None, "env": None,
            "volumes": None, **row,
        },
    )
    get_conn().commit()


def ensure_schedule(task_id: str, cron: str, timeout: int | None) -> None:
    """登记制：任务首次出现时创建 schedule（默认禁用，cron 取登记默认值）。"""
    get_conn().execute(
        """INSERT INTO task_schedules (task_id, cron, enabled, timeout_seconds)
           VALUES (?, ?, 0, ?)
           ON CONFLICT(task_id) DO NOTHING""",
        (task_id, cron, timeout),
    )
    get_conn().commit()


def list_tasks() -> list[dict]:
    rows = get_conn().execute(
        """SELECT t.*, s.cron, s.enabled, s.timeout_seconds
           FROM tasks t LEFT JOIN task_schedules s ON s.task_id = t.id
           ORDER BY t.id"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_task(task_id: str) -> dict | None:
    row = get_conn().execute(
        """SELECT t.*, s.cron, s.enabled, s.timeout_seconds
           FROM tasks t LEFT JOIN task_schedules s ON s.task_id = t.id
           WHERE t.id = ?""",
        (task_id,),
    ).fetchone()
    return dict(row) if row else None


def update_schedule(task_id: str, cron: str | None = None, enabled: bool | None = None,
                    timeout_seconds: int | None = None) -> None:
    sets, args = [], []
    if cron is not None:
        sets.append("cron=?")
        args.append(cron)
    if enabled is not None:
        sets.append("enabled=?")
        args.append(1 if enabled else 0)
    if timeout_seconds is not None:
        sets.append("timeout_seconds=?")
        args.append(timeout_seconds)
    if not sets:
        return
    args.append(task_id)
    get_conn().execute(f"UPDATE task_schedules SET {', '.join(sets)} WHERE task_id=?", args)
    get_conn().commit()


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------

def insert_run(run: dict) -> None:
    get_conn().execute(
        """INSERT INTO runs (run_id, task_id, scheduled_at, started_at, finished_at,
             duration_ms, trigger, status, exit_code, log_path, missed_schedule_at)
           VALUES (:run_id, :task_id, :scheduled_at, :started_at, :finished_at,
             :duration_ms, :trigger, :status, :exit_code, :log_path, :missed_schedule_at)""",
        run,
    )
    get_conn().commit()


def update_run(run_id: str, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    get_conn().execute(f"UPDATE runs SET {sets} WHERE run_id=?",
                       (*fields.values(), run_id))
    get_conn().commit()


def get_run(run_id: str) -> dict | None:
    row = get_conn().execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(task_id: str | None = None, status: str | None = None,
              start_from: str | None = None, start_to: str | None = None,
              limit: int = 100) -> list[dict]:
    sql = "SELECT * FROM runs WHERE 1=1"
    args: list = []
    if task_id:
        sql += " AND task_id=?"
        args.append(task_id)
    if status:
        sql += " AND status=?"
        args.append(status)
    if start_from:
        sql += " AND COALESCE(started_at, scheduled_at) >= ?"
        args.append(start_from)
    if start_to:
        sql += " AND COALESCE(started_at, scheduled_at) <= ?"
        args.append(start_to)
    sql += " ORDER BY COALESCE(started_at, scheduled_at) DESC, run_id DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in get_conn().execute(sql, args).fetchall()]


def last_run_of_task(task_id: str) -> dict | None:
    row = get_conn().execute(
        """SELECT * FROM runs WHERE task_id=? AND status NOT IN ('waiting')
           ORDER BY COALESCE(started_at, scheduled_at) DESC, run_id DESC LIMIT 1""",
        (task_id,),
    ).fetchone()
    return dict(row) if row else None


def active_run_of_task(task_id: str) -> dict | None:
    row = get_conn().execute(
        f"""SELECT * FROM runs WHERE task_id=? AND status IN {RUN_ACTIVE_STATUSES!r}
            ORDER BY run_id DESC LIMIT 1""",
        (task_id,),
    ).fetchone()
    return dict(row) if row else None


def mark_running_as_interrupted() -> int:
    """重启恢复：把遗留的 waiting/running 标记为 interrupted。"""
    cur = get_conn().execute(
        f"""UPDATE runs SET status='interrupted', finished_at=?
            WHERE status IN {RUN_ACTIVE_STATUSES!r}""",
        (now_str(),),
    )
    get_conn().commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------

def set_heartbeat(ts: str | None = None) -> None:
    get_conn().execute(
        """INSERT INTO scheduler_heartbeat (id, updated_at) VALUES (1, ?)
           ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at""",
        (ts or now_str(),),
    )
    get_conn().commit()


def get_heartbeat() -> str | None:
    row = get_conn().execute("SELECT updated_at FROM scheduler_heartbeat WHERE id=1").fetchone()
    return row["updated_at"] if row else None

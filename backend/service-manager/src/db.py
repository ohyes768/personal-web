"""SQLite 存储层（design §3）。

单文件 SQLite + WAL；每次操作短连接，事务边界显式。schema 版本写在
`runtime_state.schema_version`，未知的更高版本拒绝打开（design §9 回滚契约）。

人工台账表与观测表分开：
- 人工：services / service_components / component_overrides / endpoints /
  port_notes / release_sources / discovery_decisions
- 观测：docker_components / releases / release_sync / release_reads /
  check_results / refresh_jobs / runtime_state
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    -- 归属（我维护的 / 别人的）：逐条可设。'' = 尚未判定，启动时按旧口径回填。
    ownership TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_components (
    id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL UNIQUE,
    required INTEGER NOT NULL DEFAULT 1,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_service_components_service
    ON service_components(service_id);

-- 人工补录/覆盖的部署信息，按 source_key 存：只补充显示，不改 Docker
CREATE TABLE IF NOT EXISTS component_overrides (
    source_key TEXT PRIMARY KEY,
    working_dir TEXT,
    config_files TEXT,
    data_paths TEXT,
    version_note TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS endpoints (
    id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    label TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'external',
    url TEXT NOT NULL,
    probe_url TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    expected_status_ranges TEXT NOT NULL DEFAULT '[]',
    tls_check INTEGER NOT NULL DEFAULT 1,
    route_target TEXT,
    renewal_note TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_endpoints_service ON endpoints(service_id);

CREATE TABLE IF NOT EXISTS port_notes (
    id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    host_ip TEXT NOT NULL DEFAULT '',
    host_port INTEGER NOT NULL,
    container_port INTEGER,
    protocol TEXT NOT NULL DEFAULT 'tcp',
    note TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_port_notes_service ON port_notes(service_id);

CREATE TABLE IF NOT EXISTS release_sources (
    id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL UNIQUE REFERENCES services(id) ON DELETE CASCADE,
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    installed_tag_note TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discovery_decisions (
    source_key TEXT PRIMARY KEY,
    ignored INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

-- ---- 观测 ----

CREATE TABLE IF NOT EXISTS docker_components (
    source_key TEXT PRIMARY KEY,
    project TEXT,
    service_name TEXT,
    container_id TEXT NOT NULL DEFAULT '',
    container_name TEXT NOT NULL DEFAULT '',
    image_ref TEXT NOT NULL DEFAULT '',
    image_id TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'unknown',
    health TEXT NOT NULL DEFAULT 'unknown',
    network_mode TEXT NOT NULL DEFAULT 'bridge',
    ports TEXT NOT NULL DEFAULT '[]',
    mounts TEXT NOT NULL DEFAULT '[]',
    compose_working_dir TEXT,
    compose_files TEXT NOT NULL DEFAULT '[]',
    oneoff INTEGER NOT NULL DEFAULT 0,
    last_seen_at TEXT NOT NULL,
    scan_id INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS releases (
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    release_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    updated_at TEXT,
    body TEXT NOT NULL DEFAULT '',
    html_url TEXT NOT NULL DEFAULT '',
    prerelease INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (owner, repo, release_id)
);

CREATE TABLE IF NOT EXISTS release_sync (
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    etag TEXT,
    latest_release_id INTEGER,
    truncated INTEGER NOT NULL DEFAULT 0,
    baseline_done INTEGER NOT NULL DEFAULT 0,
    last_checked_at TEXT,
    state TEXT NOT NULL DEFAULT 'unknown',
    error TEXT,
    PRIMARY KEY (owner, repo)
);

CREATE TABLE IF NOT EXISTS release_reads (
    release_source_id TEXT NOT NULL,
    release_id INTEGER NOT NULL,
    read_at TEXT NOT NULL,
    PRIMARY KEY (release_source_id, release_id)
);

CREATE TABLE IF NOT EXISTS check_results (
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    check_kind TEXT NOT NULL,
    check_status TEXT NOT NULL DEFAULT 'never',
    current_state TEXT,
    last_attempt_at TEXT,
    last_success_at TEXT,
    last_success_payload TEXT,
    error_code TEXT,
    error_message TEXT,
    next_due_at TEXT,
    PRIMARY KEY (target_type, target_id, check_kind)
);

CREATE TABLE IF NOT EXISTS refresh_jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    target_id TEXT,
    state TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    counts TEXT NOT NULL DEFAULT '{}',
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_refresh_jobs_created ON refresh_jobs(created_at);

CREATE TABLE IF NOT EXISTS runtime_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SchemaVersionError(RuntimeError):
    """数据库 schema 版本高于本进程支持范围：拒绝打开。"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class Store:
    """SQLite 门面。线程安全：每次操作打开独立连接。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._initialized = False

    # -- 生命周期 --------------------------------------------------------

    @classmethod
    def from_settings(cls, settings: Any) -> "Store":
        data_dir: Path = settings.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        store = cls(settings.db_path)
        store.initialize()
        return store

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
                self._ensure_column(
                    conn, "services", "ownership", "TEXT NOT NULL DEFAULT ''"
                )
                stored = self._get_state(conn, "schema_version")
                if stored is None:
                    self._set_state(conn, "schema_version", str(SCHEMA_VERSION))
                    self._set_state(conn, "registry_revision", "0")
                elif int(stored) > SCHEMA_VERSION:
                    raise SchemaVersionError(
                        f"database schema {stored} is newer than supported "
                        f"{SCHEMA_VERSION}; refusing to open"
                    )
            self._initialized = True

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection, table: str, column: str, declaration: str
    ) -> None:
        """给已有库补列（CREATE TABLE IF NOT EXISTS 不会改动已存在的表）。

        追加列是向后兼容的：旧二进制读这张表时忽略未知列，所以不升 schema 版本。
        """
        existing = {
            row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
        }
        if column in existing:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self._connect() as conn:
            yield conn

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as conn:
            yield conn

    # -- runtime_state ---------------------------------------------------

    @staticmethod
    def _get_state(conn: sqlite3.Connection, key: str) -> str | None:
        row = conn.execute("SELECT value FROM runtime_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    @staticmethod
    def _set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            "INSERT INTO runtime_state(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_state(self, key: str) -> str | None:
        with self.read() as conn:
            return self._get_state(conn, key)

    def set_state(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            self._set_state(conn, key, value)

    @property
    def registry_revision(self) -> int:
        with self.read() as conn:
            return int(self._get_state(conn, "registry_revision") or 0)

    @staticmethod
    def bump_registry_revision(conn: sqlite3.Connection) -> int:
        """人工台账 mutation 在事务内调用；与实体 revision 独立。"""
        current = int(Store._get_state(conn, "registry_revision") or 0) + 1
        Store._set_state(conn, "registry_revision", str(current))
        return current

    # -- 备份 ------------------------------------------------------------

    def backup_to(self, target: Path) -> Path:
        """使用 SQLite backup API 生成一致快照（恢复前本地备份，design §7）。"""
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            src = sqlite3.connect(self.db_path, timeout=10.0)
            try:
                dst = sqlite3.connect(target)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
        return target

    # -- 维护 ------------------------------------------------------------

    def prune_jobs(self, keep_days: int = 7) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=keep_days)
        ).isoformat(timespec="seconds")
        with self.transaction() as conn:
            cur = conn.execute(
                # 只保护仍在跑的任务；queued 超期同样清理（进程重启后它们
                # 已经由 mark_running_jobs_interrupted 标成 interrupted）
                "DELETE FROM refresh_jobs WHERE created_at < ? AND state != 'running'",
                (cutoff,),
            )
            return cur.rowcount

    def mark_running_jobs_interrupted(self) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.transaction() as conn:
            cur = conn.execute(
                "UPDATE refresh_jobs SET state = 'interrupted', finished_at = ? "
                "WHERE state IN ('queued', 'running')",
                (now,),
            )
            return cur.rowcount

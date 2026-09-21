"""SQLite 运行状态库（design 3.2）。

保存发布审计、回滚快照、运行状态与登记真源（registry_skill 表）。
Skills 源库的 registry.json 不再是登记真源——它归 sync 工具链所有，
skill-manager 只在首次启动时做一次只读迁移导入，之后绝不读写该文件。

连接管理采用"每次操作短连接"：SQLite 本地文件连接创建开销极低，短连接
不跨线程共享，天然规避 FastAPI 线程池下的并发问题，因此无需
`check_same_thread=False` 与额外的锁；若未来成为瓶颈，可在不改变本类
接口的前提下切换 WAL + 每请求连接。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import Settings
from src.models import RegistrySkill

DEFAULT_DB_FILENAME = "skill-manager.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS deployment (
    skill_id            TEXT NOT NULL,
    target              TEXT NOT NULL,
    source_revision     TEXT NOT NULL DEFAULT '',
    source_path         TEXT NOT NULL,
    current_link_target TEXT NOT NULL,
    status              TEXT NOT NULL,
    published_at        TEXT NOT NULL,
    PRIMARY KEY (skill_id, target)
);

CREATE TABLE IF NOT EXISTS deployment_history (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id             TEXT NOT NULL,
    target               TEXT NOT NULL,
    action               TEXT NOT NULL,
    result               TEXT NOT NULL,
    previous_link_target TEXT,
    new_link_target      TEXT,
    source_revision      TEXT,
    error                TEXT,
    created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_skill_target
    ON deployment_history (skill_id, target, id);

CREATE TABLE IF NOT EXISTS rollback_snapshot (
    skill_id             TEXT NOT NULL,
    target               TEXT NOT NULL,
    previous_link_target TEXT NOT NULL,
    previous_revision    TEXT NOT NULL DEFAULT '',
    updated_at           TEXT NOT NULL,
    PRIMARY KEY (skill_id, target)
);

CREATE TABLE IF NOT EXISTS github_check (
    skill_id        TEXT PRIMARY KEY,
    repository      TEXT NOT NULL,
    remote_revision TEXT NOT NULL DEFAULT '',
    remote_tags     TEXT NOT NULL DEFAULT '',
    cached_revision TEXT NOT NULL DEFAULT '',
    result          TEXT NOT NULL,
    error           TEXT,
    checked_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS registry_skill (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    source      TEXT NOT NULL CHECK (source IN ('local','github')),
    path        TEXT NOT NULL,
    repository  TEXT,
    tags        TEXT NOT NULL DEFAULT '[]',
    summary     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','deprecated')),
    depends_on  TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class DeploymentRecord:
    """`deployment` 行：某 skill 在某 target 的当前部署状态。"""

    skill_id: str
    target: str
    source_revision: str
    source_path: str
    current_link_target: str
    status: str
    published_at: str


@dataclass(frozen=True)
class HistoryEntry:
    """`deployment_history` 行：一次发布/下架/回滚的审计记录（只追加）。"""

    skill_id: str
    target: str
    action: str
    result: str
    previous_link_target: str | None
    new_link_target: str | None
    source_revision: str | None
    error: str | None
    created_at: str


@dataclass(frozen=True)
class RollbackSnapshot:
    """`rollback_snapshot` 行：某 skill × target 上一次可恢复的链接目标。"""

    skill_id: str
    target: str
    previous_link_target: str
    previous_revision: str
    updated_at: str


@dataclass(frozen=True)
class GithubCheckRecord:
    """`github_check` 行：某 GitHub Skill 最近一次手动更新检查结果。"""

    skill_id: str
    repository: str
    remote_revision: str
    remote_tags: str
    cached_revision: str
    result: str
    error: str | None
    checked_at: str


class SkillStateStore:
    """deployment / deployment_history / rollback_snapshot 的唯一读写入口。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)

    @classmethod
    def from_settings(cls, settings: Settings) -> "SkillStateStore":
        """生产入口：数据库文件路径由 Settings.state_dir 派生。"""
        return cls(settings.state_dir / DEFAULT_DB_FILENAME)

    # ---------- deployment ----------

    def upsert_deployment(self, record: DeploymentRecord) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO deployment
                    (skill_id, target, source_revision, source_path,
                     current_link_target, status, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.skill_id,
                    record.target,
                    record.source_revision,
                    record.source_path,
                    record.current_link_target,
                    record.status,
                    record.published_at,
                ),
            )

    def get_deployment(self, skill_id: str, target: str) -> DeploymentRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM deployment WHERE skill_id = ? AND target = ?",
                (skill_id, target),
            ).fetchone()
        return _row_to_deployment(row) if row is not None else None

    def list_deployments(self) -> list[DeploymentRecord]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM deployment ORDER BY skill_id, target"
            ).fetchall()
        return [_row_to_deployment(row) for row in rows]

    # ---------- deployment_history（只追加） ----------

    def append_history(self, entry: HistoryEntry) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO deployment_history
                    (skill_id, target, action, result, previous_link_target,
                     new_link_target, source_revision, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.skill_id,
                    entry.target,
                    entry.action,
                    entry.result,
                    entry.previous_link_target,
                    entry.new_link_target,
                    entry.source_revision,
                    entry.error,
                    entry.created_at,
                ),
            )

    def list_history(
        self,
        skill_id: str | None = None,
        target: str | None = None,
        limit: int = 200,
    ) -> list[HistoryEntry]:
        query = "SELECT * FROM deployment_history"
        conditions: list[str] = []
        params: list[Any] = []
        if skill_id is not None:
            conditions.append("skill_id = ?")
            params.append(skill_id)
        if target is not None:
            conditions.append("target = ?")
            params.append(target)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id LIMIT ?"
        params.append(limit)
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_history(row) for row in rows]

    # ---------- rollback_snapshot ----------

    def set_rollback_snapshot(self, snapshot: RollbackSnapshot) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO rollback_snapshot
                    (skill_id, target, previous_link_target, previous_revision,
                     updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.skill_id,
                    snapshot.target,
                    snapshot.previous_link_target,
                    snapshot.previous_revision,
                    snapshot.updated_at,
                ),
            )

    def get_rollback_snapshot(
        self, skill_id: str, target: str
    ) -> RollbackSnapshot | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM rollback_snapshot WHERE skill_id = ? AND target = ?",
                (skill_id, target),
            ).fetchone()
        return _row_to_snapshot(row) if row is not None else None

    def delete_rollback_snapshot(self, skill_id: str, target: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "DELETE FROM rollback_snapshot WHERE skill_id = ? AND target = ?",
                (skill_id, target),
            )

    def delete_rollback_snapshots(self, skill_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "DELETE FROM rollback_snapshot WHERE skill_id = ?", (skill_id,)
            )

    # ---------- github_check ----------

    def upsert_github_check(self, record: GithubCheckRecord) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO github_check
                    (skill_id, repository, remote_revision, remote_tags,
                     cached_revision, result, error, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.skill_id,
                    record.repository,
                    record.remote_revision,
                    record.remote_tags,
                    record.cached_revision,
                    record.result,
                    record.error,
                    record.checked_at,
                ),
            )

    def get_github_check(self, skill_id: str) -> GithubCheckRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM github_check WHERE skill_id = ?", (skill_id,)
            ).fetchone()
        return _row_to_github_check(row) if row is not None else None

    def delete_github_check(self, skill_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "DELETE FROM github_check WHERE skill_id = ?", (skill_id,)
            )

    # ---------- registry_skill（登记真源） ----------

    def list_registry_skills(self) -> list[RegistrySkill]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM registry_skill ORDER BY id"
            ).fetchall()
        return [_row_to_registry_skill(row) for row in rows]

    def get_registry_skill(self, skill_id: str) -> RegistrySkill | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM registry_skill WHERE id = ?", (skill_id,)
            ).fetchone()
        return _row_to_registry_skill(row) if row is not None else None

    def upsert_registry_skill(self, skill: RegistrySkill) -> None:
        """同 id 替换；created_at 保留首次写入值，updated_at 每次刷新。"""
        now = _utcnow_iso()
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT created_at FROM registry_skill WHERE id = ?", (skill.id,)
            ).fetchone()
            created_at = row["created_at"] if row is not None else now
            conn.execute(
                """
                INSERT OR REPLACE INTO registry_skill
                    (id, name, source, path, repository, tags, summary, status,
                     depends_on, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill.id,
                    skill.name,
                    skill.source.value,
                    skill.path,
                    str(skill.repository) if skill.repository else None,
                    json.dumps(skill.tags, ensure_ascii=False),
                    skill.summary,
                    skill.status,
                    json.dumps(skill.depends_on, ensure_ascii=False),
                    created_at,
                    now,
                ),
            )

    def delete_registry_skill(self, skill_id: str) -> bool:
        """删除登记条目，返回该 id 是否原本存在。"""
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "DELETE FROM registry_skill WHERE id = ?", (skill_id,)
            )
        return cursor.rowcount > 0

    def count_registry_skills(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM registry_skill"
            ).fetchone()
        return int(row["n"])

    # ---------- 内部 ----------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _row_to_deployment(row: sqlite3.Row) -> DeploymentRecord:
    return DeploymentRecord(
        skill_id=row["skill_id"],
        target=row["target"],
        source_revision=row["source_revision"],
        source_path=row["source_path"],
        current_link_target=row["current_link_target"],
        status=row["status"],
        published_at=row["published_at"],
    )


def _row_to_history(row: sqlite3.Row) -> HistoryEntry:
    return HistoryEntry(
        skill_id=row["skill_id"],
        target=row["target"],
        action=row["action"],
        result=row["result"],
        previous_link_target=row["previous_link_target"],
        new_link_target=row["new_link_target"],
        source_revision=row["source_revision"],
        error=row["error"],
        created_at=row["created_at"],
    )


def _row_to_snapshot(row: sqlite3.Row) -> RollbackSnapshot:
    return RollbackSnapshot(
        skill_id=row["skill_id"],
        target=row["target"],
        previous_link_target=row["previous_link_target"],
        previous_revision=row["previous_revision"],
        updated_at=row["updated_at"],
    )


def _row_to_github_check(row: sqlite3.Row) -> GithubCheckRecord:
    return GithubCheckRecord(
        skill_id=row["skill_id"],
        repository=row["repository"],
        remote_revision=row["remote_revision"],
        remote_tags=row["remote_tags"],
        cached_revision=row["cached_revision"],
        result=row["result"],
        error=row["error"],
        checked_at=row["checked_at"],
    )


def _row_to_registry_skill(row: sqlite3.Row) -> RegistrySkill:
    return RegistrySkill(
        id=row["id"],
        name=row["name"],
        source=row["source"],
        path=row["path"],
        repository=row["repository"],
        tags=json.loads(row["tags"]),
        summary=row["summary"],
        status=row["status"],
        depends_on=json.loads(row["depends_on"]),
    )


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()

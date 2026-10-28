"""轮廓工作流持久化:任务、候选、人工覆盖层与操作记录同库同事务。

放在 DATA_DIR/boundary_workflow.sqlite3,与小区注册库相互独立 —— 人工确认结果不写基础
轮廓文件,后台重建基础轮廓不会吞掉人工结果。表结构:

  jobs        生成任务(阶段、输入指纹、错误分类)
  candidates  候选轮廓(GCJ02 环、参考建筑、面积、质量提示、状态)
  overrides   人工确认覆盖层(每个小区至多一条)
  operations  应用/撤销操作记录(带 operation_id,用于幂等重放)
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.services.data_loader import DATA_DIR

WORKFLOW_DB = DATA_DIR / "boundary_workflow.sqlite3"

def _now() -> str:
    from src.services.community_registry import now
    return now()


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class BoundaryWorkflowStore:
    def __init__(self, path: Path | str = WORKFLOW_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    community_id TEXT NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    candidate_id TEXT,
                    refresh_buildings INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS jobs_community ON jobs(community_id, phase);
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    community_id TEXT NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    base_revision TEXT NOT NULL,
                    effective_revision TEXT NOT NULL,
                    rings TEXT NOT NULL,
                    reference_buildings TEXT NOT NULL,
                    area_ha REAL,
                    building_faces INTEGER,
                    residential_faces INTEGER,
                    low_confidence INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL,
                    warnings TEXT NOT NULL DEFAULT '[]',
                    estimated_at TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS candidates_community ON candidates(community_id, status);
                CREATE TABLE IF NOT EXISTS overrides (
                    community_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    rings TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    community_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    candidate_id TEXT,
                    before_revision TEXT,
                    after_revision TEXT,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS operations_community ON operations(community_id, created_at);
            ''')

    @contextmanager
    def db(self):
        with sqlite3.connect(self.path, timeout=15) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db

    # -- jobs ---------------------------------------------------------------

    def insert_job(self, job_id: str, community_id: str, fingerprint: str,
                   refresh_buildings: bool = False) -> None:
        with self.db() as db:
            db.execute(
                'INSERT INTO jobs(job_id, community_id, input_fingerprint, phase, refresh_buildings,'
                ' created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                (job_id, community_id, fingerprint, 'queued', int(refresh_buildings), _now(), _now()),
            )

    def update_job(self, job_id: str, *, phase: str | None = None, error_code: str | None = None,
                   error_message: str | None = None, candidate_id: str | None = None) -> None:
        fields, values = [], []
        if phase is not None:
            fields.append('phase=?')
            values.append(phase)
        if error_code is not None:
            fields.append('error_code=?')
            values.append(error_code)
        if error_message is not None:
            fields.append('error_message=?')
            values.append(error_message)
        if candidate_id is not None:
            fields.append('candidate_id=?')
            values.append(candidate_id)
        if not fields:
            return
        fields.append('updated_at=?')
        values.append(_now())
        values.append(job_id)
        with self.db() as db:
            db.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE job_id=?", values)

    def job(self, job_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()
        return dict(row) if row else None

    def active_job(self, community_id: str, fingerprint: str) -> dict | None:
        """同小区同输入的在途任务(排队或执行中)。"""
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE community_id=? AND input_fingerprint=?"
                " AND phase IN ('queued','reading','fetching','estimating')"
                " ORDER BY created_at DESC LIMIT 1",
                (community_id, fingerprint),
            ).fetchone()
        return dict(row) if row else None

    def latest_job(self, community_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute(
                'SELECT * FROM jobs WHERE community_id=? ORDER BY created_at DESC LIMIT 1',
                (community_id,),
            ).fetchone()
        return dict(row) if row else None

    def interrupt_stale_jobs(self) -> int:
        """启动恢复:排队/执行中的任务标记为中断,不再自动向外网发请求。"""
        with self.db() as db:
            cursor = db.execute(
                "UPDATE jobs SET phase='interrupted', error_code='interrupted',"
                " error_message='服务重启导致任务中断', updated_at=? "
                "WHERE phase IN ('queued','reading','fetching','estimating')",
                (_now(),),
            )
            return cursor.rowcount

    # -- candidates ---------------------------------------------------------

    def complete_job_with_candidate(self, *, job_id: str, candidate_id: str, community_id: str,
                                    fingerprint: str, base_revision: str, effective_revision: str,
                                    rings, reference_buildings, area_ha: float, building_faces: int,
                                    residential_faces: int, low_confidence: bool, source: str,
                                    warnings, estimated_at: str) -> None:
        """候选入库与任务置为成功必须同事务,避免出现"任务成功但没有候选"。"""
        with self.db() as db:
            db.execute(
                'INSERT INTO candidates(candidate_id, job_id, community_id, input_fingerprint,'
                ' base_revision, effective_revision, rings, reference_buildings, area_ha,'
                ' building_faces, residential_faces, low_confidence, source, warnings,'
                ' estimated_at, created_at, status)'
                ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (candidate_id, job_id, community_id, fingerprint, base_revision, effective_revision,
                 _dump(rings), _dump(reference_buildings), area_ha, building_faces, residential_faces,
                 int(low_confidence), source, _dump(list(warnings)), estimated_at, _now(), 'ready'),
            )
            db.execute("UPDATE jobs SET phase='succeeded', candidate_id=?, updated_at=? WHERE job_id=?",
                       (candidate_id, _now(), job_id))

    def candidate(self, candidate_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute('SELECT * FROM candidates WHERE candidate_id=?', (candidate_id,)).fetchone()
        return dict(row) if row else None

    def ready_candidate(self, community_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM candidates WHERE community_id=? AND status='ready'"
                " ORDER BY created_at DESC LIMIT 1",
                (community_id,),
            ).fetchone()
        return dict(row) if row else None

    def set_candidate_status(self, candidate_id: str, status: str) -> None:
        with self.db() as db:
            db.execute('UPDATE candidates SET status=? WHERE candidate_id=?', (status, candidate_id))

    def supersede_ready_candidates(self, community_id: str) -> int:
        """重新生成时把旧的待应用候选置为 superseded。"""
        with self.db() as db:
            cursor = db.execute(
                "UPDATE candidates SET status='superseded' WHERE community_id=? AND status='ready'",
                (community_id,),
            )
            return cursor.rowcount

    # -- overrides ----------------------------------------------------------

    def override(self, community_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute('SELECT * FROM overrides WHERE community_id=?', (community_id,)).fetchone()
        return dict(row) if row else None

    def all_overrides(self) -> dict[str, dict]:
        with self.db() as db:
            rows = db.execute('SELECT * FROM overrides').fetchall()
        return {row['community_id']: dict(row) for row in rows}

    # -- 原子操作: 覆盖层 + 候选状态 + 操作记录必须同事务 -------------------

    def apply_candidate_atomic(self, *, community_id: str, candidate_id: str, rings, source: str,
                               operation_id: str, before_revision: str, after_revision: str,
                               result, supersede_candidate_id: str | None = None) -> int:
        """写入人工覆盖层、置候选为 applied、记录操作,三件事同事务。"""
        with self.db() as db:
            row = db.execute('SELECT revision FROM overrides WHERE community_id=?',
                             (community_id,)).fetchone()
            revision = (row['revision'] + 1) if row else 1
            db.execute(
                'INSERT OR REPLACE INTO overrides(community_id, candidate_id, rings, source,'
                ' confirmed_at, revision) VALUES (?,?,?,?,?,?)',
                (community_id, candidate_id, _dump(rings), source, _now(), revision),
            )
            if supersede_candidate_id:
                db.execute("UPDATE candidates SET status='superseded' WHERE candidate_id=?",
                           (supersede_candidate_id,))
            db.execute("UPDATE candidates SET status='applied' WHERE candidate_id=?", (candidate_id,))
            db.execute(
                'INSERT OR REPLACE INTO operations(operation_id, community_id, kind, candidate_id,'
                ' before_revision, after_revision, result, created_at) VALUES (?,?,?,?,?,?,?,?)',
                (operation_id, community_id, 'apply', candidate_id, before_revision, after_revision,
                 _dump(result), _now()),
            )
            return revision

    def revert_candidate_atomic(self, *, community_id: str, candidate_id: str, operation_id: str,
                                before_revision: str, after_revision: str, result) -> None:
        """删除人工覆盖层、置候选为 reverted、记录操作,三件事同事务。"""
        with self.db() as db:
            db.execute('DELETE FROM overrides WHERE community_id=?', (community_id,))
            db.execute("UPDATE candidates SET status='reverted' WHERE candidate_id=?", (candidate_id,))
            db.execute(
                'INSERT OR REPLACE INTO operations(operation_id, community_id, kind, candidate_id,'
                ' before_revision, after_revision, result, created_at) VALUES (?,?,?,?,?,?,?,?)',
                (operation_id, community_id, 'revert', candidate_id, before_revision, after_revision,
                 _dump(result), _now()),
            )

    # -- operations ---------------------------------------------------------

    def operation(self, operation_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute('SELECT * FROM operations WHERE operation_id=?', (operation_id,)).fetchone()
        return dict(row) if row else None

    def latest_operation(self, community_id: str, kind: str) -> dict | None:
        with self.db() as db:
            row = db.execute(
                'SELECT * FROM operations WHERE community_id=? AND kind=? ORDER BY created_at DESC LIMIT 1',
                (community_id, kind),
            ).fetchone()
        return dict(row) if row else None

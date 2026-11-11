"""刷新任务（design §6 调度与手动刷新）。

- 手动刷新创建持久化 job，返回 job_id（端点返回 202）
- 同一 kind+target 正在运行 → 复用现有 job（deduplicated=true）
- 每类任务互斥且有超时；一项失败不阻断其他服务
- 重启把旧 running job 标 interrupted，然后按 next_due_at 恢复
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from src.db import Store
from src.errors import bad_request, not_found
from src.models import JobState, RefreshJobView, RefreshKind

JobRunner = Callable[[RefreshKind, str | None, "JobContext"], Awaitable[dict[str, int]]]


@dataclass
class JobContext:
    job_id: str
    kind: RefreshKind
    target_id: str | None
    cancelled: threading.Event = field(default_factory=threading.Event)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobManager:
    def __init__(self, store: Store) -> None:
        self.store = store
        self._lock = threading.RLock()
        self._running: dict[tuple[str, str | None], str] = {}
        self._contexts: dict[str, JobContext] = {}
        self._runners: dict[RefreshKind, JobRunner] = {}

    def register(self, kind: RefreshKind, runner: JobRunner) -> None:
        self._runners[kind] = runner

    # -- 持久化 ----------------------------------------------------------

    def _insert(self, kind: RefreshKind, target_id: str | None) -> str:
        job_id = str(uuid.uuid4())
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO refresh_jobs(id, kind, target_id, state, created_at,"
                " counts, error) VALUES (?,?,?,?,?,?,?)",
                (job_id, kind.value, target_id, JobState.QUEUED.value, _now(), "{}", None),
            )
        return job_id

    def find_active(self, kind: RefreshKind, target_id: str | None) -> str | None:
        with self.store.read() as conn:
            row = conn.execute(
                "SELECT id FROM refresh_jobs WHERE kind = ? AND"
                " (target_id IS ? OR target_id = ?) AND state IN ('queued','running')"
                " ORDER BY created_at DESC LIMIT 1",
                (kind.value, target_id, target_id),
            ).fetchone()
        return row["id"] if row else None

    def _set_state(
        self,
        job_id: str,
        state: JobState,
        *,
        counts: dict[str, int] | None = None,
        error: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> None:
        fields = ["state = ?"]
        params: list[Any] = [state.value]
        if started:
            fields.append("started_at = ?")
            params.append(_now())
        if finished:
            fields.append("finished_at = ?")
            params.append(_now())
        if counts is not None:
            import json

            fields.append("counts = ?")
            params.append(json.dumps(counts, ensure_ascii=False))
        if error is not None:
            fields.append("error = ?")
            params.append(error)
        params.append(job_id)
        with self.store.transaction() as conn:
            conn.execute(
                f"UPDATE refresh_jobs SET {', '.join(fields)} WHERE id = ?", params
            )

    def _view(self, row) -> RefreshJobView:
        import json

        return RefreshJobView(
            id=row["id"],
            kind=RefreshKind(row["kind"]),
            target_id=row["target_id"],
            state=JobState(row["state"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            counts=json.loads(row["counts"] or "{}"),
            error=row["error"],
        )

    def get(self, job_id: str) -> RefreshJobView:
        with self.store.read() as conn:
            row = conn.execute(
                "SELECT * FROM refresh_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise not_found("任务不存在")
        return self._view(row)

    def list(self, *, limit: int = 20) -> list[RefreshJobView]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT * FROM refresh_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._view(row) for row in rows]

    # -- 创建 / 执行 -----------------------------------------------------

    def create(
        self, kind: RefreshKind, target_id: str | None = None
    ) -> tuple[RefreshJobView, bool]:
        """返回 (job, deduplicated)。"""
        if kind == RefreshKind.DOCKER and target_id:
            raise bad_request(
                "docker 刷新不接受 target_id", {"target_id": "docker 刷新不接受 target_id"}
            )
        if kind not in self._runners:
            raise bad_request(f"未注册的刷新类型: {kind}")
        with self._lock:
            active = self.find_active(kind, target_id)
            if active is not None:
                view = self.get(active)
                view.deduplicated = True
                return view, True
            job_id = self._insert(kind, target_id)
            self._running[(kind.value, target_id)] = job_id
        return self.get(job_id), False

    async def run(self, job_id: str) -> RefreshJobView:
        view = self.get(job_id)
        ctx = JobContext(job_id=job_id, kind=view.kind, target_id=view.target_id)
        self._contexts[job_id] = ctx
        self._set_state(job_id, JobState.RUNNING, started=True)
        runner = self._runners[view.kind]
        try:
            counts = await asyncio.wait_for(
                runner(view.kind, view.target_id, ctx), timeout=180
            )
            state = (
                JobState.COMPLETED
                if counts.get("failed", 0) == 0
                else JobState.PARTIAL_FAILED
                if counts.get("succeeded", 0) > 0
                else JobState.FAILED
            )
            self._set_state(job_id, state, counts=counts, finished=True)
        except asyncio.TimeoutError:
            self._set_state(
                job_id,
                JobState.FAILED,
                error="任务超时（180s）",
                finished=True,
            )
        except asyncio.CancelledError:
            self._set_state(job_id, JobState.INTERRUPTED, error="任务被取消", finished=True)
            raise
        except Exception as exc:  # noqa: BLE001 - 单个任务失败不阻断其他
            self._set_state(job_id, JobState.FAILED, error=str(exc), finished=True)
        finally:
            self._contexts.pop(job_id, None)
            with self._lock:
                self._running.pop((view.kind.value, view.target_id), None)
        return self.get(job_id)

    def recover_interrupted(self) -> int:
        return self.store.mark_running_jobs_interrupted()

    def prune(self, keep_days: int = 7) -> int:
        return self.store.prune_jobs(keep_days=keep_days)

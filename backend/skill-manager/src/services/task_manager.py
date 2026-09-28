"""GitHub 后台任务管理器（design §2 / PRD R1-R5）。

进程内内存态：daemon 线程执行 + 锁保护快照，不引入 Celery/Redis/任务
持久化；容器重启丢任务由 task_not_found 兜底（PRD Constraints）。

- 任务上下文只携带 RegistrySkill 与 canonical URL——管理密码在路由同步
  段校验后即丢弃，绝不进入本模块任何结构（R2/R3/AC5）；
- 对外只发冻结 TaskSnapshot；内部可变对象仅本模块持有；
- 完结任务保留 30 分钟，查询时惰性回收（无定时器线程，R4）；
- 进度节流：同一 stage 且同一 percent 的重复帧不推进 updated_at
  （`git --progress` 同一百分比会重复刷帧，design §1）。

错误映射与第一阶段路由一致：GitTimeoutError → download_timeout、
UnreachableRepositoryError → unreachable、RegistryValidationError →
registry_conflict、其余 GitCacheError 按 kind → scan_failed/cache_failed、
非预期异常 → internal_error（logger.exception 记录堆栈）；error_message
沿用第一阶段 HTTPException 的中文文案（PRD R9），前端直接展示。
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Literal

from src.models import RegistrySkill
from src.services.git_cache import (
    GitCacheError,
    GitCacheService,
    GitProgress,
    GitTimeoutError,
    UnreachableRepositoryError,
)
from src.services.registry import RegistryService, RegistryValidationError

logger = logging.getLogger(__name__)

TaskKind = Literal["scan", "register", "clone_cache"]
TaskState = Literal["running", "done", "error"]

# 完结任务保留时长；超过后查询时惰性删除（PRD R4）
_RETENTION_SECONDS = 30 * 60

# 错误文案与第一阶段 HTTPException 逐字一致（PRD R9：错误码沿用第一阶段
# 文案，AC3"下载超时：……可稍后重试"），前端按 message 直接展示
_UNREACHABLE_MESSAGE = "仓库不存在或当前网络无法访问"
_DOWNLOAD_TIMEOUT_MESSAGE = "下载超时：仓库较大或当前网络较慢，可稍后重试"


@dataclass(frozen=True)
class TaskSnapshot:
    """任务快照：三种任务（scan/register/clone_cache）共用的只读视图。

    `candidates` 仅 scan 且 state=done 时非空；`stage` 取值
    remote_check / receiving / resolving / discover / registry。
    """

    task_id: str
    kind: TaskKind
    repository: str
    skill_id: str | None
    state: TaskState
    stage: str
    progress_percent: int | None
    progress_detail: str
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    candidates: tuple[str, ...] = ()


@dataclass
class _MutableTask:
    """TaskManager 内部持有的可变任务态；字段更新一律持锁进行。"""

    task_id: str
    kind: TaskKind
    repository: str
    skill: RegistrySkill | None
    skill_id: str | None
    created_at: float
    updated_at: float
    state: TaskState = "running"
    stage: str = "remote_check"
    progress_percent: int | None = None
    progress_detail: str = ""
    error_code: str | None = None
    error_message: str | None = None
    candidates: tuple[str, ...] = ()


def _apply_progress(
    task: _MutableTask,
    phase: str,
    percent: int | None,
    detail: str,
    now: float,
) -> bool:
    """写入一帧进度；同 phase 同 percent 的重复帧返回 False 且不推进
    updated_at（节流，design §1：TaskManager 侧同一 percent 不重复写）。"""
    if task.stage == phase and task.progress_percent == percent:
        return False
    task.stage = phase
    task.progress_percent = percent
    task.progress_detail = detail
    task.updated_at = now
    return True


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


def _snapshot_of(task: _MutableTask) -> TaskSnapshot:
    return TaskSnapshot(
        task_id=task.task_id,
        kind=task.kind,
        repository=task.repository,
        skill_id=task.skill_id,
        state=task.state,
        stage=task.stage,
        progress_percent=task.progress_percent,
        progress_detail=task.progress_detail,
        error_code=task.error_code,
        error_message=task.error_message,
        created_at=_iso(task.created_at),
        updated_at=_iso(task.updated_at),
        candidates=task.candidates,
    )


def _cache_error_code(kind: TaskKind) -> str:
    return "scan_failed" if kind == "scan" else "cache_failed"


def _cache_error_message(kind: TaskKind, exc: GitCacheError) -> str:
    """cache 类错误文案按任务取第一阶段路由的同款措辞。"""
    if kind == "scan":
        return f"扫描失败：{exc}"
    if kind == "register":
        return f"GitHub 仓库缓存失败：{exc}"
    return f"GitHub 缓存更新失败：{exc}"


class GithubTaskManager:
    """内存态 GitHub 任务表：创建即启动 daemon 线程，查询返回冻结快照。"""

    def __init__(
        self,
        git_cache: GitCacheService,
        registry: RegistryService,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._git_cache = git_cache
        self._registry = registry
        self._clock = clock
        self._tasks: dict[str, _MutableTask] = {}
        self._lock = threading.Lock()

    # ---------- 创建 ----------

    def start_scan(self, repository: str) -> TaskSnapshot:
        """创建扫描任务；canonical 化失败同步抛 InvalidRepositoryError。"""
        return self._create(
            kind="scan",
            repository=self._git_cache.normalize_repository(repository),
        )

    def start_register(self, skill: RegistrySkill) -> TaskSnapshot:
        """创建登记任务（缓存落地 + 注册表 upsert）。"""
        return self._create(
            kind="register", repository=str(skill.repository), skill=skill
        )

    def start_clone(self, skill: RegistrySkill) -> TaskSnapshot:
        """创建 Clone 缓存任务（语义与登记流程一致，design 5）。"""
        return self._create(
            kind="clone_cache", repository=str(skill.repository), skill=skill
        )

    # ---------- 查询 ----------

    def get(self, task_id: str) -> TaskSnapshot | None:
        """返回任务快照；完结任务超过保留窗口后惰性回收（返回 None）。

        不存在/已回收一律 None，由路由层映射为 task_not_found（R4）。
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            if (
                task.state != "running"
                and self._clock() - task.updated_at > _RETENTION_SECONDS
            ):
                del self._tasks[task_id]
                return None
            return _snapshot_of(task)

    # ---------- 内部：创建与线程分派 ----------

    def _create(
        self,
        kind: TaskKind,
        repository: str,
        skill: RegistrySkill | None = None,
    ) -> TaskSnapshot:
        task_id = uuid.uuid4().hex
        now = self._clock()
        task = _MutableTask(
            task_id=task_id,
            kind=kind,
            repository=repository,
            skill=skill,
            skill_id=skill.id if skill is not None else None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._tasks[task_id] = task
            snapshot = _snapshot_of(task)
        logger.info(
            "task %s created: kind=%s repository=%s skill=%s",
            task_id,
            kind,
            repository,
            task.skill_id,
        )
        threading.Thread(
            target=self._run,
            args=(task_id,),
            name=f"github-task-{kind}-{task_id[:8]}",
            daemon=True,
        ).start()
        return snapshot

    def _run(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            return
        try:
            candidates = self._execute(task_id, task)
        except GitTimeoutError:
            self._fail(task_id, "download_timeout", _DOWNLOAD_TIMEOUT_MESSAGE)
        except UnreachableRepositoryError:
            self._fail(task_id, "unreachable", _UNREACHABLE_MESSAGE)
        except RegistryValidationError as exc:
            self._fail(task_id, "registry_conflict", f"注册表写入被拒绝：{exc}")
        except GitCacheError as exc:
            self._fail(
                task_id,
                _cache_error_code(task.kind),
                _cache_error_message(task.kind, exc),
            )
        except Exception as exc:
            logger.exception("task %s (%s) crashed unexpectedly", task_id, task.kind)
            self._fail(task_id, "internal_error", f"内部错误：{type(exc).__name__}")
        else:
            self._complete(task_id, candidates)

    # ---------- 内部：三种任务的执行体（design §2） ----------

    def _execute(self, task_id: str, task: _MutableTask) -> tuple[str, ...]:
        if task.kind == "scan":
            return self._execute_scan(task_id, task)
        if task.kind == "register":
            self._execute_register(task_id, task)
            return ()
        self._execute_clone(task_id, task)
        return ()

    def _execute_scan(
        self, task_id: str, task: _MutableTask
    ) -> tuple[str, ...]:
        self._set_stage(task_id, "remote_check")
        self._git_cache.verify_reachable(task.repository)
        scanned = self._git_cache.scan(
            task.repository, on_progress=self._progress_sink(task_id)
        )
        self._set_stage(task_id, "discover")
        return tuple(candidate.path for candidate in scanned)

    def _execute_register(self, task_id: str, task: _MutableTask) -> None:
        skill = self._require_skill(task_id, task)
        self._set_stage(task_id, "remote_check")
        self._git_cache.verify_reachable(task.repository)
        info = self._git_cache.check_update(skill)
        self._git_cache.ensure_cached(
            skill,
            info.remote_revision,
            on_progress=self._progress_sink(task_id),
        )
        self._set_stage(task_id, "registry")
        self._registry.upsert(skill)

    def _execute_clone(self, task_id: str, task: _MutableTask) -> None:
        skill = self._require_skill(task_id, task)
        self._set_stage(task_id, "remote_check")
        self._git_cache.verify_reachable(task.repository)
        info = self._git_cache.check_update(skill)
        self._git_cache.ensure_cached(
            skill,
            info.remote_revision,
            on_progress=self._progress_sink(task_id),
        )

    def _require_skill(self, task_id: str, task: _MutableTask) -> RegistrySkill:
        if task.skill is None:
            raise RuntimeError(f"task {task_id} ({task.kind}) is missing its skill")
        return task.skill

    # ---------- 内部：状态推进 ----------

    def _progress_sink(
        self, task_id: str
    ) -> Callable[[GitProgress], None]:
        """把 git 进度帧写入任务态（持锁；节流见 `_apply_progress`）。"""

        def on_progress(frame: GitProgress) -> None:
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None or task.state != "running":
                    return
                _apply_progress(
                    task,
                    frame.phase,
                    frame.percent,
                    frame.detail,
                    self._clock(),
                )

        return on_progress

    def _set_stage(self, task_id: str, stage: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.state != "running":
                return
            task.stage = stage
            task.updated_at = self._clock()

    def _complete(self, task_id: str, candidates: tuple[str, ...]) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.state = "done"
            task.candidates = candidates
            task.updated_at = self._clock()
        logger.info("task %s done: kind=%s candidates=%d", task_id, task.kind, len(candidates))

    def _fail(self, task_id: str, code: str, message: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            kind = task.kind
            task.state = "error"
            task.error_code = code
            task.error_message = message
            task.updated_at = self._clock()
        logger.warning("task %s failed: kind=%s code=%s", task_id, kind, code)

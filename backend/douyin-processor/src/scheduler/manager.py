"""scheduler 管理器：注册 / 启停 / 立即执行 / 历史（douyin-processor 版）

参照 backend/dividend-select/src/scheduler/manager.py 移植，按 douyin 实际适配：

- job 定义来自 jobs.JOB_SPECS（代码注册表）；cron 来自 config/app.yaml
  （host 只读挂载，改后 restart 生效，recreate 不丢）
- enabled 状态持久化到 data/scheduler/enabled.json（douyin-data 卷，recreate/rebuild 都不丢）
- 一个逻辑 job 可对应多个 cron 时刻（如 process_pending 的 09:45/17:15）：
  内部按 `{job_id}#{i}` 注册多个 APScheduler 子 job（3.x add_job 不支持 trigger 列表），
  共享同一 wrapper，UI 仍呈现为一张卡
- target 为进程内直调（不走 dividend 的 HTTP self-call，无端口探活）
- shutdown drain 契约遵循 .trellis/spec/backend/dividend-select/backend/scheduler-lifecycle.md
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.events import EVENT_SCHEDULER_SHUTDOWN
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from loguru import logger

from src.scheduler.cron_human import cron_to_human
from src.scheduler.history import JSONLReaderWriter, build_record
from src.scheduler.jobs import JOB_SPECS, JOB_TARGETS

# crontab 表达式统一按 Asia/Shanghai 解析。APScheduler 的 from_crontab 不传
# timezone 会落到系统默认时区（容器内为 UTC），导致触发时间偏移 8 小时。
# scheduler 与每个 trigger 必须共用同一时区。
# dow 数字陷阱：APScheduler 3.x 的 CronTrigger 0=周一，不是 crontab 的 0=周日。
SCHEDULER_TIMEZONE = "Asia/Shanghai"


class SchedulerManager:
    """内建 APScheduler 管理器（douyin 版）。

    - 启动时从 JOB_SPECS + app.yaml cron 组装 2 个逻辑 job，注册到 AsyncIOScheduler
    - MemoryJobStore（默认，零持久化）
    - 启用/禁用立即生效，且写回 data/scheduler/enabled.json overlay
    - 立即执行用 DateTrigger 一次性触发（trigger=manual），cron job 不受影响
    """

    def __init__(self, app_config: dict, data_dir: Path, services: dict) -> None:
        pp = app_config.get("process_pending", {})
        cleanup = app_config.get("cleanup", {})
        self._timezone = pp.get("timezone") or cleanup.get("timezone") or SCHEDULER_TIMEZONE
        self._cron_map: dict[str, list[str]] = {
            "process_pending": [
                pp.get("cron_morning", "45 9 * * *"),
                pp.get("cron_evening", "15 17 * * *"),
            ],
            "cleanup_old_records": [cleanup.get("cron", "7 3 * * *")],
        }
        self._data_dir = Path(data_dir) / "scheduler"
        self._enabled_path = self._data_dir / "enabled.json"
        self._history = JSONLReaderWriter(self._data_dir / "history.jsonl")
        self._services = services
        self.jobs_meta: dict[str, dict] = {}
        # job_id → asyncio.Lock（防 trigger_now 与 cron 重入）
        self._run_locks: dict[str, asyncio.Lock] = {}
        self._scheduler: AsyncIOScheduler | None = None
        self._running_tasks: set[asyncio.Task] = set()
        self._closing = False
        self._shutdown_lock = asyncio.Lock()

    # === lifecycle ===

    def start(self) -> None:
        """启动 scheduler。services 需含 processor 与 cleanup_days。"""
        if self._scheduler is not None:
            logger.warning("scheduler 已启动，忽略 start")
            return
        self._assert_single_worker()
        self._closing = False

        overlay = self._load_enabled_overlay()
        self.jobs_meta = {}
        for spec in JOB_SPECS:
            job_id = spec["id"]
            crons = self._cron_map.get(job_id) or []
            if not crons:
                logger.error(f"[{job_id}] 未在 app.yaml 找到 cron 配置，跳过注册")
                continue
            self.jobs_meta[job_id] = {
                **spec,
                "crons": crons,
                "enabled": overlay.get(job_id, True),
            }
            self._run_locks[job_id] = asyncio.Lock()

        scheduler = AsyncIOScheduler(
            timezone=self._timezone,
            job_defaults={
                "max_instances": 1,
                "coalesce": True,
                "misfire_grace_time": 3600,
            },
        )
        registered = 0
        for job_id, spec in self.jobs_meta.items():
            triggers: list[CronTrigger] = []
            for cron in spec["crons"]:
                try:
                    triggers.append(CronTrigger.from_crontab(cron, timezone=self._timezone))
                except Exception as e:
                    logger.error(f"[{job_id}] cron 解析失败: {cron!r} ({e})")
            if not triggers:
                continue
            for i, trigger in enumerate(triggers):
                # APScheduler 3.x add_job 不支持 trigger 列表 → 每 cron 一个子 job
                scheduler.add_job(
                    self._run_job_wrapper,
                    trigger,
                    id=f"{job_id}#{i}",
                    args=[job_id],
                    replace_existing=True,
                )
            if not spec["enabled"]:
                self._pause_sub_jobs(scheduler, job_id)
            registered += 1
            logger.info(
                f"[{job_id}] 注册: crons={spec['crons']} "
                f"({' / '.join(cron_to_human(c) for c in spec['crons'])}) "
                f"enabled={spec['enabled']} target={spec['target']}"
            )
        scheduler.start()
        self._scheduler = scheduler
        logger.info(f"scheduler 启动完成，{registered} 个逻辑任务")

    async def shutdown(self, wait: bool = True, timeout: int = 30) -> None:
        """Stop admission, drain jobs within the deadline, then stop APScheduler.

        APScheduler 3.x's asyncio executor cancels jobs even with wait=True;
        draining must happen before calling its shutdown method.
        """
        async with self._shutdown_lock:
            scheduler = self._scheduler
            if scheduler is None:
                return
            self._closing = True
            scheduler.pause()
            logger.info(f"scheduler 关闭中（wait={wait}, timeout={timeout}s）...")
            stopped = asyncio.Event()
            scheduler.add_listener(lambda event: stopped.set(), EVENT_SCHEDULER_SHUTDOWN)
            try:
                pending = set(self._running_tasks)
                if wait and pending:
                    _, pending = await asyncio.wait(pending, timeout=max(0, timeout))
                    if pending:
                        logger.warning(f"scheduler drain 超时，取消 {len(pending)} 个任务")
            finally:
                # This also cancels executor submissions that have not entered
                # the wrapper yet. Await the scheduled shutdown callback.
                scheduler.shutdown(wait=False)
                await stopped.wait()
                await asyncio.sleep(0)  # let cooperative cancellation release locks
            self._scheduler = None

    # === API ===

    def list_jobs(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for job_id, spec in self.jobs_meta.items():
            sub_jobs = self._sched_sub_jobs(job_id)
            next_run_times = [
                j.next_run_time for j in sub_jobs if j.next_run_time is not None
            ]
            next_run = min(next_run_times).isoformat() if next_run_times else None
            last_runs = self._history.read_tail(job_id=job_id, n=1)
            last_run = last_runs[0] if last_runs else None
            result.append(
                {
                    "id": job_id,
                    "name": spec.get("name", job_id),
                    "target": spec["target"],
                    "crons": spec["crons"],
                    "cron_human": " / ".join(cron_to_human(c) for c in spec["crons"]),
                    "enabled": spec.get("enabled", True),
                    "next_run_time": next_run,
                    "last_run": _slim_last_run(last_run),
                    "description": spec.get("description", ""),
                }
            )
        return result

    def set_enabled(self, job_id: str, enabled: bool) -> dict[str, Any]:
        if job_id not in self.jobs_meta:
            raise KeyError(job_id)
        if self._scheduler is None or self._closing:
            raise RuntimeError("scheduler 未启动")
        self.jobs_meta[job_id]["enabled"] = enabled
        self._write_enabled_overlay()
        if enabled:
            self._resume_sub_jobs(self._scheduler, job_id)
            logger.info(f"[{job_id}] 已启用")
        else:
            self._pause_sub_jobs(self._scheduler, job_id)
            logger.info(f"[{job_id}] 已禁用")
        # 返回更新后的 job（list_jobs 重新读 history 拿 last_run）
        return next(j for j in self.list_jobs() if j["id"] == job_id)

    def trigger_now(self, job_id: str, trigger: str = "manual") -> dict[str, Any]:
        if job_id not in self.jobs_meta:
            raise KeyError(job_id)
        if self._scheduler is None or self._closing:
            raise RuntimeError("scheduler 未启动")
        triggered_at = datetime.now().isoformat()
        # 一次性任务：用 DateTrigger 立即触发；id 加后缀避免与 cron 子 job 冲突
        run_id = f"{job_id}#manual_{int(datetime.now().timestamp() * 1000)}"
        self._scheduler.add_job(
            self._run_job_wrapper,
            DateTrigger(run_date=datetime.now()),
            id=run_id,
            args=[job_id, trigger],
            replace_existing=False,
        )
        logger.info(f"[{job_id}] 手动触发 @ {triggered_at} (run_id={run_id}, trigger={trigger})")
        return {"job_id": job_id, "triggered_at": triggered_at}

    def get_job_runs(self, job_id: str, limit: int = 20) -> list[dict[str, Any]]:
        if job_id not in self.jobs_meta:
            raise KeyError(job_id)
        return self._history.read_tail(job_id=job_id, n=limit)

    # === helpers ===

    def _sched_sub_jobs(self, job_id: str, scheduler: AsyncIOScheduler | None = None) -> list:
        """取某逻辑 job 的全部 APScheduler 子 job。

        scheduler 缺省读 self._scheduler；start() 阶段需显式传入（此时 self._scheduler 尚未赋值）。
        """
        sched = scheduler if scheduler is not None else self._scheduler
        if sched is None:
            return []
        prefix = f"{job_id}#"
        return [j for j in sched.get_jobs() if j.id.startswith(prefix)]

    def _pause_sub_jobs(self, scheduler: AsyncIOScheduler, job_id: str) -> None:
        for sub in self._sched_sub_jobs(job_id, scheduler):
            scheduler.pause_job(sub.id)

    def _resume_sub_jobs(self, scheduler: AsyncIOScheduler, job_id: str) -> None:
        for sub in self._sched_sub_jobs(job_id, scheduler):
            scheduler.resume_job(sub.id)

    def _load_enabled_overlay(self) -> dict[str, bool]:
        try:
            with open(self._enabled_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {k: bool(v) for k, v in (data or {}).items()}
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.warning(f"读取 enabled.json 失败，按全启用处理: {e}")
            return {}

    def _write_enabled_overlay(self) -> None:
        """把全部 job 的 enabled 状态原子写回 overlay（tmp + os.replace）。"""
        overlay = {job_id: spec.get("enabled", True) for job_id, spec in self.jobs_meta.items()}
        try:
            self._enabled_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._enabled_path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(overlay, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._enabled_path)
        except Exception as e:
            logger.error(f"enabled.json 写回失败（页面状态与运行态可能不一致）: {e}")

    def _assert_single_worker(self) -> None:
        """多 worker 启动时拒绝（沿 dividend NFR-4：scheduler 必须单 worker）。"""
        workers_str = os.environ.get("WEB_CONCURRENCY") or os.environ.get("UVICORN_WORKERS")
        if workers_str and workers_str.isdigit() and int(workers_str) > 1:
            raise RuntimeError(
                f"scheduler 要求单 worker 模式，检测到 workers={workers_str}。"
                "请用 --workers 1 或 unset WEB_CONCURRENCY/UVICORN_WORKERS"
            )

    async def _run_job_wrapper(self, job_id: str, trigger: str = "scheduled") -> None:
        """APScheduler 调用入口：查 target → 调 jobs.{target} → 写历史。"""
        if self._closing:
            return
        task = asyncio.current_task()
        assert task is not None
        self._running_tasks.add(task)
        try:
            await self._execute_job(job_id, trigger)
        finally:
            self._running_tasks.discard(task)

    async def _execute_job(self, job_id: str, trigger: str = "scheduled") -> None:
        spec = self.jobs_meta.get(job_id)
        if spec is None:
            logger.warning(f"未知 job_id: {job_id}")
            return
        target_name = spec["target"]
        target_fn = JOB_TARGETS.get(target_name)
        if target_fn is None:
            logger.error(f"[{job_id}] 未知 target: {target_name}")
            return
        # 防重入：cron 触发 vs trigger_now 同时进来时串行化
        lock = self._run_locks.setdefault(job_id, asyncio.Lock())
        async with lock:
            if self._closing:
                return
            logger.info(f"[{job_id}] 开始执行 target={target_name} trigger={trigger}")
            start = datetime.now().isoformat()
            try:
                result = await target_fn(self._services, job_id, trigger)
            except Exception as e:
                logger.exception(f"[{job_id}] target 抛异常")
                now_iso = datetime.now().isoformat()
                result = {
                    "status": "failed",
                    "error": f"unhandled: {e}",
                }
            end = datetime.now().isoformat()
            record = build_record(
                job_id=job_id,
                target=target_name,
                trigger=trigger,
                start=start,
                end=end,
                status=result.get("status", "failed"),
                count=result.get("count"),
                reason=result.get("reason"),
                error=result.get("error"),
                failed=result.get("failed"),
            )
            await self._history.append(record)
            logger.info(
                f"[{job_id}] 执行结束 status={record['status']} trigger={trigger} "
                f"count={record.get('count')} reason={record.get('reason')}"
            )


def _slim_last_run(rec: dict | None) -> dict | None:
    """精简 last_run 字段（job_id/target/trigger 已在 job 顶层或历史里）。"""
    if rec is None:
        return None
    return {
        "trigger": rec.get("trigger"),
        "start": rec.get("start"),
        "end": rec.get("end"),
        "status": rec.get("status"),
        "count": rec.get("count"),
        "reason": rec.get("reason"),
        "error": rec.get("error"),
    }

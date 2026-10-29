"""
APScheduler 管理器

调度任务由 scheduler.json 配置：每周串行更新四个 tab。
"""
import asyncio
import json
from collections import deque
from copy import deepcopy
from pathlib import Path
from threading import Lock
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.utils.config import DATA_DIR, PROJECT_ROOT
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.scheduler")

SCHEDULER_CONFIG = PROJECT_ROOT / "src" / "scheduler" / "scheduler.json"


class SchedulerManager:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self.state_dir = state_dir if state_dir is not None else DATA_DIR / "scheduler"
        self.history_path = self.state_dir / "weekly_refresh.jsonl"
        self.settings_path = self.state_dir / "settings.json"
        self.jobs_meta: dict[str, dict] = {}
        self._running = False
        self._current_run: dict | None = None
        self._last_record: dict | None = None
        self._snapshot_lock = Lock()
        self._background_tasks: set[asyncio.Task] = set()

    def start(self, app) -> None:
        config = json.loads(SCHEDULER_CONFIG.read_text(encoding="utf-8"))
        settings = json.loads(self.settings_path.read_text(encoding="utf-8")) if self.settings_path.exists() else {}
        for job in config["jobs"]:
            job = {**job, "enabled": settings.get(job["id"], job.get("enabled", True))}
            self.jobs_meta[job["id"]] = job
            if job["target"] != "refresh_weekly":
                raise ValueError(f"未知定时任务 target: {job['target']}")
            self.scheduler.add_job(
                self._weekly_refresh,
                CronTrigger.from_crontab(job["cron"], timezone="Asia/Shanghai"),
                id=job["id"], name=job["name"], replace_existing=True,
                max_instances=1, coalesce=True, misfire_grace_time=3600,
            )
            if not job["enabled"]:
                self.scheduler.pause_job(job["id"])
            logger.info("注册定时任务 %s @ %s Asia/Shanghai", job["id"], job["cron"])
        self.scheduler.start()
        logger.info("Scheduler 已启动")

    async def _weekly_refresh(self) -> None:
        if self._running:
            logger.info("每周任务已在运行，跳过重复调度")
            return
        self._reserve("scheduled")
        await self._execute_reserved()

    def _reserve(self, trigger: str) -> None:
        from src.scheduler.weekly_refresh import _now
        self._running = True
        self._update_snapshot({"run_id": str(uuid4()), "trigger": trigger,
                               "start": _now(), "status": "running", "items": []})

    def _update_snapshot(self, record: dict) -> None:
        with self._snapshot_lock:
            self._current_run = deepcopy(record)

    async def _execute_reserved(self) -> None:
        from src.scheduler.weekly_refresh import refresh_weekly_sync
        with self._snapshot_lock:
            initial = deepcopy(self._current_run)
        logger.info("每周四个 tab 刷新开始")
        try:
            result = await asyncio.to_thread(
                refresh_weekly_sync, history_path=self.history_path,
                trigger=initial["trigger"], run_id=initial["run_id"],
                on_progress=self._update_snapshot,
            )
            self._last_record = result
        except Exception as exc:
            from src.scheduler.weekly_refresh import _now
            with self._snapshot_lock:
                self._last_record = {**self._current_run, "status": "failed", "end": _now(), "error": str(exc)}
            logger.exception("每周刷新失败")
        finally:
            self._running = False
        logger.info("每周四个 tab 刷新结束 status=%s", self._last_record["status"])

    def _require_job(self, job_id: str) -> dict:
        if job_id not in self.jobs_meta:
            raise KeyError(job_id)
        return self.jobs_meta[job_id]

    def list_jobs(self) -> list[dict]:
        result = []
        for job_id, spec in self.jobs_meta.items():
            job = self.scheduler.get_job(job_id)
            next_run = getattr(job, "next_run_time", None)
            if spec["enabled"] and job is not None and not hasattr(job, "next_run_time"):
                from src.scheduler.weekly_refresh import TIMEZONE
                from datetime import datetime
                next_run = job.trigger.get_next_fire_time(None, datetime.now(TIMEZONE))
            runs = self.get_job_runs(job_id, 1)
            with self._snapshot_lock:
                current = deepcopy(self._current_run) if self._running else None
            result.append({**spec, "cron_human": "每周六 07:05（北京时间）",
                           "timezone": "Asia/Shanghai", "running": self._running,
                           "next_run_time": next_run.isoformat() if next_run else None,
                           "current_run": current, "last_run": self._last_record or (runs[0] if runs else None)})
        return result

    def _save_settings(self, settings: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.settings_path)

    def set_enabled(self, job_id: str, enabled: bool) -> dict:
        spec = self._require_job(job_id)
        self._save_settings({key: enabled if key == job_id else value["enabled"]
                             for key, value in self.jobs_meta.items()})
        if enabled:
            self.scheduler.resume_job(job_id)
        else:
            self.scheduler.pause_job(job_id)
        spec["enabled"] = enabled
        return next(job for job in self.list_jobs() if job["id"] == job_id)

    async def trigger_now(self, job_id: str) -> dict:
        self._require_job(job_id)
        if self._running:
            raise ValueError("任务正在运行，请等待本轮结束")
        self._reserve("manual")
        task = asyncio.create_task(self._execute_reserved())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return {"status": "running", "job_id": job_id}

    def get_job_runs(self, job_id: str, limit: int = 20) -> list[dict]:
        self._require_job(job_id)
        if not self.history_path.exists():
            return []
        records: deque = deque(maxlen=limit)
        with self.history_path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict) and record.get("job_id", job_id) == job_id:
                    records.append(record)
        return list(reversed(records))

    async def shutdown(self, wait: bool = False) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)

"""
调度器：APScheduler 单实例 + 心跳 + 漏执行补记 + 重启恢复。

漏执行识别（不补跑）：每分钟 tick 时，对每个启用任务枚举上次记录点之后的
应执行时间；若该时间没有对应 run 记录，补一条 status=interrupted、
missed_schedule_at=应执行时间 的记录，留证不补发。

调度记录点：每个任务在 task_schedules 上没有专门字段，用
"该任务最后一次 scheduled 触发的 scheduled_at" 作为枚举起点；没有历史时
从 now-1 个调度窗口内开始（保守：起点取 now-24h）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db, executor

logger = logging.getLogger("task-web.scheduler")

TICK_SECONDS = 60
MISS_SCAN_WINDOW_HOURS = 24


class TaskScheduler:
    def __init__(self, timezone: str = "Asia/Shanghai") -> None:
        self.tz = ZoneInfo(timezone)
        self.scheduler = BackgroundScheduler(timezone=str(self.tz))
        self._reload_lock = __import__("threading").Lock()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """启动：先恢复旧运行状态，再按当前 schedule 注册任务。"""
        recovered = db.mark_running_as_interrupted()
        if recovered:
            logger.warning("重启恢复：把 %d 条遗留 waiting/running 标记为 interrupted", recovered)
        db.set_heartbeat()
        self.reload_jobs()
        self.scheduler.add_job(
            self._tick, "interval", seconds=TICK_SECONDS,
            id="heartbeat-tick", max_instances=1, coalesce=True,
        )
        self.scheduler.start()

    def shutdown(self) -> None:
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass

    # -- jobs ---------------------------------------------------------------

    def reload_jobs(self) -> int:
        """按 task_schedules 全量重建 cron job（修改调度后调用）。"""
        with self._reload_lock:
            for job in self.scheduler.get_jobs():
                if job.id != "heartbeat-tick":
                    job.remove()
            n = 0
            for t in db.list_tasks():
                if not t.get("enabled") or not t.get("cron"):
                    continue
                try:
                    trigger = CronTrigger.from_crontab(t["cron"], timezone=str(self.tz))
                except ValueError as e:
                    logger.error("任务 %s cron 非法(%s): %s", t["id"], t["cron"], e)
                    continue
                self.scheduler.add_job(
                    self._fire_scheduled, trigger=trigger,
                    id=f"task-{t['id']}", args=[t["id"]],
                    max_instances=1, coalesce=True,
                    misfire_grace_time=60,
                )
                n += 1
            logger.info("已注册 %d 个定时任务", n)
            return n

    def next_fire_time(self, task_id: str) -> str | None:
        for job in self.scheduler.get_jobs():
            if job.id == f"task-{task_id}":
                nxt = job.trigger.get_next_fire_time(None, datetime.now(self.tz))
                return nxt.isoformat(timespec="seconds") if nxt else None
        return None

    # -- firing -------------------------------------------------------------

    def _fire_scheduled(self, task_id: str) -> None:
        task = db.get_task(task_id)
        if not task or not task.get("enabled"):
            return
        scheduled_at = db.now_str()
        executor.start_run(task, trigger="scheduled", scheduled_at=scheduled_at)

    # -- tick / heartbeat / miss detection ----------------------------------

    def _tick(self) -> None:
        db.set_heartbeat()
        try:
            self._detect_missed()
        except Exception:
            logger.exception("漏执行检测异常")

    def _detect_missed(self) -> None:
        for t in db.list_tasks():
            if not t.get("enabled") or not t.get("cron"):
                continue
            try:
                trigger = CronTrigger.from_crontab(t["cron"], timezone=str(self.tz))
            except ValueError:
                continue
            now = datetime.now(self.tz)
            start = self._scan_start(t["id"], now)
            expected: list[datetime] = []
            cur = start
            for _ in range(200):  # 防御性上限
                nxt = trigger.get_next_fire_time(cur, now)
                if nxt is None or nxt > now:
                    # 上界必须显式判断：传 previous 后 get_next_fire_time 忽略 now，
                    # 否则会把未来触发点也补记成"漏执行"
                    break
                expected.append(nxt)
                cur = nxt
            for fire in expected:
                # 归一为 naive 本地串：与 scheduled_at / 库内其余时间戳同格式，
                # 否则 _has_run_for_schedule 永不匹配，已执行的时刻会被补记成假漏执行
                fire_str = db.naive_local(fire.isoformat(timespec="seconds"))
                if self._has_run_for_schedule(t["id"], fire_str):
                    continue
                db.insert_run({
                    "run_id": db.new_run_id(t["id"]), "task_id": t["id"],
                    "scheduled_at": None, "started_at": None, "finished_at": db.now_str(),
                    "duration_ms": None, "trigger": "scheduled", "status": "interrupted",
                    "exit_code": None, "log_path": None, "missed_schedule_at": fire_str,
                })
                logger.warning("任务 %s 漏执行：%s 无对应运行记录", t["id"], fire_str)

    def _scan_start(self, task_id: str, now: datetime) -> datetime:
        last = db.last_run_of_task(task_id)
        if last and last.get("trigger") == "scheduled" and last.get("scheduled_at"):
            try:
                return datetime.fromisoformat(last["scheduled_at"]).replace(tzinfo=self.tz)
            except ValueError:
                pass
        return now - timedelta(hours=MISS_SCAN_WINDOW_HOURS)

    @staticmethod
    def _has_run_for_schedule(task_id: str, fire_str: str) -> bool:
        # scheduled 触发的 run 或漏执行补记，任一存在即视为已记录；
        # 补记可能是修复前写入的带时区格式，统一归一后再比较
        rows = db.list_runs(task_id=task_id, limit=500)
        for r in rows:
            if db.naive_local(r.get("missed_schedule_at")) == fire_str:
                return True
            if r.get("trigger") == "scheduled" and r.get("scheduled_at") == fire_str:
                return True
        return False

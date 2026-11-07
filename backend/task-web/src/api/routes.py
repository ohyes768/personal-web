"""
task-web REST API（router 前缀 /api，nginx 剥 /api/task-web 后对上）
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import db, executor
from ..config import get_admin_password, get_log_dir, get_log_retention_days
from ..scheduler import TaskScheduler

logger = logging.getLogger("task-web.api")

router = APIRouter()

# main 启动时注入
scheduler: TaskScheduler | None = None


class ScheduleUpdate(BaseModel):
    cron: str | None = None
    enabled: bool | None = None
    timeout_seconds: int | None = None


class ManualRunRequest(BaseModel):
    password: str


def _effective_profile(t: dict) -> str | None:
    """AI 任务的生效 Hermes profile（只读推导，不改表）。

    推导规则（与 tasks.yaml 注释及 .env 约定一致）：
    - env 显式 HERMES_PROFILE → 该值（防漂移，显式声明优先）；
    - env_file 为 .env.hermes-default → default profile（gateway 8642）；
    - env_file 为 .env → ohyes768（.env 默认 profile，gateway 8643）；
    - 其余（非 Hermes 触发的 AI 任务 / 脚本任务）→ None。
    """
    if (t.get("group_name") or "script") != "ai":
        return None
    try:
        env = json.loads(t["env"]) if t.get("env") else {}
    except (TypeError, ValueError):
        env = {}
    explicit = env.get("HERMES_PROFILE")
    if explicit:
        return str(explicit)
    env_file = t.get("env_file") or ""
    if env_file.endswith(".env.hermes-default"):
        return "default"
    if env_file.endswith("/.env") or env_file == ".env":
        return "ohyes768"
    return None


def _task_view(t: dict) -> dict:
    last = db.last_run_of_task(t["id"])
    active = db.active_run_of_task(t["id"])
    nxt = scheduler.next_fire_time(t["id"]) if scheduler else None
    return {
        "id": t["id"],
        "name": t["name"],
        "description": t["description"],
        "command": t["command"],
        "cwd": t["cwd"],
        "volumes": json.loads(t["volumes"]) if t.get("volumes") else [],
        "network": t.get("network"),
        "user": t.get("run_user"),
        "group": t.get("group_name") or "script",
        "profile": _effective_profile(t),
        "targets": json.loads(t["targets"]) if t.get("targets") else [],
        "cron": t.get("cron"),
        "enabled": bool(t.get("enabled")),
        "timeout_seconds": t.get("timeout_seconds") or t.get("default_timeout"),
        "last_run": last,
        "active_run": active,
        "next_fire_time": nxt,
    }


@router.get("/health")
def health():
    return {"status": "ok", "heartbeat": db.get_heartbeat()}


@router.get("/tasks")
def list_tasks():
    tasks = [_task_view(t) for t in db.list_tasks()]
    return {"total": len(tasks), "tasks": tasks}


@router.put("/tasks/{task_id}/schedule")
def update_schedule(task_id: str, body: ScheduleUpdate):
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, f"任务不存在: {task_id}")
    if body.cron is not None:
        from apscheduler.triggers.cron import CronTrigger

        try:
            CronTrigger.from_crontab(body.cron)
        except ValueError as e:
            raise HTTPException(400, f"cron 表达式非法: {e}")
    db.update_schedule(task_id, cron=body.cron, enabled=body.enabled,
                       timeout_seconds=body.timeout_seconds)
    if scheduler:
        scheduler.reload_jobs()
    return _task_view(db.get_task(task_id))


@router.post("/tasks/{task_id}/run")
def manual_run(task_id: str, body: ManualRunRequest):
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, f"任务不存在: {task_id}")
    expected = get_admin_password()
    if not expected:
        raise HTTPException(403, "未配置 TASK_WEB_ADMIN_PASSWORD，手动执行已禁用")
    if body.password != expected:
        raise HTTPException(401, "密码错误")
    run_id = executor.start_run(task, trigger="manual")
    return {"run_id": run_id}


@router.get("/runs")
def list_runs_api(
    task_id: str | None = Query(None),
    status: str | None = Query(None),
    start_from: str | None = Query(None, alias="from"),
    start_to: str | None = Query(None, alias="to"),
    limit: int = Query(100, le=500),
):
    runs = db.list_runs(task_id=task_id, status=status,
                        start_from=start_from, start_to=start_to, limit=limit)
    return {"total": len(runs), "runs": runs}


# 排期日历接口（/schedule/summary、/schedule/day）待 src/schedule.py 与其依赖的
# db.naive_local / db.summary_rows / db.day_runs 一起提交后再启用；
# c8bc7c35 只提交了本文件的引用，模块未入库，master 起不来。

@router.get("/runs/{run_id}")
def get_run_api(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, f"运行记录不存在: {run_id}")
    return run


@router.get("/runs/{run_id}/logs")
def run_logs(run_id: str, offset: int = Query(0, ge=0)):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, f"运行记录不存在: {run_id}")
    result: dict = {"run_id": run_id, "offset": offset, "stdout": "", "stderr": ""}
    for key, ext in (("stdout", "out"), ("stderr", "err")):
        p: Path = get_log_dir() / f"{run_id}.{ext}"
        if not p.exists():
            continue
        size = p.stat().st_size
        with open(p, "rb") as fh:
            fh.seek(min(offset, size))
            chunk = fh.read(64 * 1024)
        result[key] = chunk.decode("utf-8", errors="replace")
    result["size"] = {
        "stdout": (get_log_dir() / f"{run_id}.out").stat().st_size
        if (get_log_dir() / f"{run_id}.out").exists() else 0,
        "stderr": (get_log_dir() / f"{run_id}.err").stat().st_size
        if (get_log_dir() / f"{run_id}.err").exists() else 0,
    }
    return result


@router.post("/maintenance/cleanup-logs")
def cleanup_logs():
    """按保留天数清理日志文件（运行记录保留，只删文件）。手动触发。"""
    import time

    cutoff = time.time() - get_log_retention_days() * 86400
    removed = 0
    for p in get_log_dir().glob("*"):
        if p.is_file() and p.stat().st_mtime < cutoff:
            p.unlink()
            removed += 1
    return {"removed": removed, "retention_days": get_log_retention_days()}

"""验收用 API 测试：health / 任务列表 / 调度修改 / 手动执行 / runs / 日志。"""
from __future__ import annotations

import time

from src import db


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_tasks_registered(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    r = client.get("/api/tasks")
    body = r.json()
    assert body["total"] == 2
    ids = {t["id"] for t in body["tasks"]}
    assert ids == {"demo-success", "demo-failure"}
    # 导入默认禁用
    assert all(t["enabled"] is False for t in body["tasks"])


def test_update_schedule_validates_cron(client):
    r = client.put("/api/tasks/demo-success/schedule",
                   json={"cron": "not-a-cron"})
    assert r.status_code == 400
    r = client.put("/api/tasks/demo-success/schedule",
                   json={"cron": "*/5 * * * *", "enabled": True})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["cron"] == "*/5 * * * *"


def test_manual_run_requires_password(client):
    r = client.post("/api/tasks/demo-success/run", json={"password": "wrong"})
    assert r.status_code == 401
    r = client.post("/api/tasks/demo-success/run", json={"password": "test-pass"})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    # 等执行线程结束
    for _ in range(50):
        run = db.get_run(run_id)
        if run["status"] not in ("waiting", "running"):
            break
        time.sleep(0.1)
    assert run["status"] == "success"
    assert run["exit_code"] == 0
    assert run["trigger"] == "manual"


def test_failure_run_records_exit_code(client):
    r = client.post("/api/tasks/demo-failure/run", json={"password": "test-pass"})
    run_id = r.json()["run_id"]
    for _ in range(50):
        run = db.get_run(run_id)
        if run["status"] not in ("waiting", "running"):
            break
        time.sleep(0.1)
    assert run["status"] == "failed"
    assert run["exit_code"] == 3


def test_mutex_skip(client):
    """第二个并发触发应记 skipped 而不是并发执行。"""
    from src import executor

    task = db.get_task("demo-success")
    task["command"] = "sleep 2" if _is_posix() else "ping -n 2 127.0.0.1"
    db.upsert_task({**task})
    run1 = executor.start_run(task, trigger="manual")
    run2 = executor.start_run(task, trigger="scheduled", scheduled_at=db.now_str())
    assert db.get_run(run2)["status"] == "skipped"
    assert db.get_run(run1)["status"] in ("waiting", "running", "success")


def test_run_logs_endpoint(client):
    r = client.post("/api/tasks/demo-success/run", json={"password": "test-pass"})
    run_id = r.json()["run_id"]
    for _ in range(50):
        if db.get_run(run_id)["status"] not in ("waiting", "running"):
            break
        time.sleep(0.1)
    r = client.get(f"/api/runs/{run_id}/logs")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body["stdout"]


def test_runs_filter(client):
    r = client.get("/api/runs", params={"status": "success"})
    assert r.status_code == 200
    assert all(x["status"] == "success" for x in r.json()["runs"])


def test_restart_recovery_marks_interrupted(env):
    from src import db as dbm

    run_id = dbm.new_run_id("demo-success")
    dbm.insert_run({
        "run_id": run_id, "task_id": "demo-success", "scheduled_at": None,
        "started_at": dbm.now_str(), "finished_at": None, "duration_ms": None,
        "trigger": "manual", "status": "running", "exit_code": None,
        "log_path": None, "missed_schedule_at": None,
    })
    from src.scheduler import TaskScheduler

    s = TaskScheduler(timezone="Asia/Shanghai")
    recovered = s.__class__ and _recover(s)
    assert recovered >= 1
    assert dbm.get_run(run_id)["status"] == "interrupted"


def _recover(scheduler) -> int:
    from src import db as dbm

    return dbm.mark_running_as_interrupted()


def _is_posix() -> bool:
    import os

    return os.name == "posix"

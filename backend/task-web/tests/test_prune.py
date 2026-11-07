"""登记修剪：yaml 里移除的任务应从 DB 清理（调度删、运行历史保留）。"""
from __future__ import annotations

from pathlib import Path

from src import db, registry


def test_prune_removes_absent_tasks(client, env):
    Path(env["tasks_yaml"]).write_text(
        'tasks:\n  - id: keep-a\n    name: a\n    command: echo a\n'
        '  - id: drop-b\n    name: b\n    command: echo b\n', encoding="utf-8")
    registry.sync_registry()
    assert db.get_task("keep-a") and db.get_task("drop-b")

    # 第二次同步：drop-b 从 yaml 移除
    Path(env["tasks_yaml"]).write_text(
        'tasks:\n  - id: keep-a\n    name: a\n    command: echo a\n', encoding="utf-8")
    registry.sync_registry()

    assert db.get_task("keep-a") is not None
    assert db.get_task("drop-b") is None
    assert db.get_heartbeat() is not None  # DB 仍可用


def test_prune_keeps_run_history(client, env):
    Path(env["tasks_yaml"]).write_text(
        'tasks:\n  - id: gone\n    name: g\n    command: echo g\n', encoding="utf-8")
    registry.sync_registry()
    run_id = db.new_run_id("gone")
    db.insert_run({
        "run_id": run_id, "task_id": "gone", "scheduled_at": None,
        "started_at": db.now_str(), "finished_at": None, "duration_ms": None,
        "trigger": "manual", "status": "success", "exit_code": 0,
        "log_path": None, "missed_schedule_at": None,
    })

    Path(env["tasks_yaml"]).write_text("tasks: []\n", encoding="utf-8")
    registry.sync_registry()

    assert db.get_task("gone") is None
    assert db.get_run(run_id)["status"] == "success"  # 历史不丢

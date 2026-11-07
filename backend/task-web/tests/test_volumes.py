"""volumes 支持（11-06-hermes-unified-trigger）：解析、校验、SDK 传参。"""
from __future__ import annotations

import json

import pytest

from src import executor


def test_parse_volumes_defaults_ro():
    assert executor.parse_volumes(["/a:/b"]) == ["/a:/b:ro"]
    assert executor.parse_volumes(["/a:/b:ro", "/c:/d:rw"]) == ["/a:/b:ro", "/c:/d:rw"]


def test_parse_volumes_json_string(env):
    assert executor.parse_volumes(json.dumps(["/x:/y:ro"])) == ["/x:/y:ro"]


def test_parse_volumes_rejects_bad():
    with pytest.raises(ValueError, match="volumes 条目非法"):
        executor.parse_volumes(["/only-src"])
    with pytest.raises(ValueError, match="mode 非法"):
        executor.parse_volumes(["/a:/b:xx"])
    with pytest.raises(ValueError, match="volumes 字段非法"):
        executor.parse_volumes("not-json")


def test_docker_run_passes_volumes(env, monkeypatch):
    from tests.test_engine import FakeClient, FakeContainer

    fc = FakeClient(FakeContainer(exit_code=0))
    monkeypatch.setattr(executor, "_get_docker_client", lambda: fc)
    run_id = executor.db.new_run_id("demo")
    executor.db.insert_run({
        "run_id": run_id, "task_id": "demo", "scheduled_at": None,
        "started_at": None, "finished_at": None, "duration_ms": None,
        "trigger": "manual", "status": "waiting", "exit_code": None,
        "log_path": None, "missed_schedule_at": None,
    })
    task = {"id": "demo", "command": "x", "engine": "docker",
            "image": "img", "timeout_seconds": 30,
            "volumes": ["/home/ohyes768/skills:/hermes-skills:ro"]}
    executor.execute_docker_run(run_id, task, 30)
    assert fc.last_kwargs["volumes"] == ["/home/ohyes768/skills:/hermes-skills:ro"]


def test_registry_passes_volumes(client, env):
    """registry 同步后 volumes 入库并可在 API 读到。"""
    from pathlib import Path

    Path(env["tasks_yaml"]).write_text(
        """tasks:
  - id: vol-task
    name: v
    command: echo hi
    engine: docker
    image: img
    volumes:
      - "/src:/dst:ro"
""", encoding="utf-8")
    from src import registry

    registry.sync_registry()
    task = executor.db.get_task("vol-task")
    assert json.loads(task["volumes"]) == ["/src:/dst:ro"]

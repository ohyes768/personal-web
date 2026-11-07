"""volumes 支持（11-06-hermes-unified-trigger）：登记校验、docker-py 传参、入库读取。

合并说明：两条并行实现已合并——登记层校验 registry._parse_volumes（允许裸挂载，
不注入默认模式）来自 docker-engine 提交；执行层转换 executor._task_volumes
（裸挂载默认 rw）与 volumes 列迁移来自 hermes-unified-trigger 提交。
测试按合并后的行为重写。
"""
from __future__ import annotations

import json

import pytest

from src import executor, registry


def test_parse_volumes_keeps_explicit_mode():
    assert registry._parse_volumes(["/a:/b:ro", "/c:/d:rw"]) == ["/a:/b:ro", "/c:/d:rw"]


def test_parse_volumes_allows_bare_bind():
    # 登记层不注入默认模式，裸「宿主:容器」原样保留；执行层按 rw 处理。
    assert registry._parse_volumes(["/a:/b"]) == ["/a:/b"]


def test_parse_volumes_rejects_bad():
    with pytest.raises(ValueError, match="volumes 条目非法"):
        registry._parse_volumes(["/only-src"])
    with pytest.raises(ValueError, match="volumes 挂载模式只支持"):
        registry._parse_volumes(["/a:/b:xx"])
    with pytest.raises(ValueError, match="volumes 必须是字符串列表"):
        registry._parse_volumes("not-a-list")


def test_task_volumes_converts_to_sdk_dict():
    # 入参是 task dict（volumes 可能是登记后的 JSON 字符串或已解析列表）。
    assert executor._task_volumes({"volumes": ["/a:/b"]}) == {"/a": {"bind": "/b", "mode": "rw"}}
    assert executor._task_volumes({"volumes": json.dumps(["/x:/y:ro"])}) == {"/x": {"bind": "/y", "mode": "ro"}}
    assert executor._task_volumes({}) == {}


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
    assert fc.last_kwargs["volumes"] == {"/home/ohyes768/skills": {"bind": "/hermes-skills", "mode": "ro"}}


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

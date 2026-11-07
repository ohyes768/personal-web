"""group 分组（script/hermes）：登记校验与 API 透出。"""
from __future__ import annotations

from pathlib import Path

from src import registry


def _sync(env, yaml_text):
    Path(env["tasks_yaml"]).write_text(yaml_text, encoding="utf-8")
    return registry.sync_registry()


def test_group_default_script(client, env):
    _sync(env, 'tasks:\n  - id: t1\n    name: x\n    command: echo hi\n')
    from src import db

    assert db.get_task("t1")["group_name"] == "script"


def test_group_ai_stored(client, env):
    _sync(env, 'tasks:\n  - id: t2\n    name: x\n    group: ai\n    command: python t.py\n')
    from src import db

    assert db.get_task("t2")["group_name"] == "ai"


def test_group_legacy_hermes_alias(client, env):
    """旧值 hermes 兼容映射为 ai。"""
    _sync(env, 'tasks:\n  - id: t2b\n    name: x\n    group: hermes\n    command: python t.py\n')
    from src import db

    assert db.get_task("t2b")["group_name"] == "ai"


def test_group_invalid_rejected(client, env):
    try:
        _sync(env, 'tasks:\n  - id: t3\n    name: x\n    group: bogus\n    command: x\n')
    except ValueError as e:
        assert "group 非法" in str(e)
    else:
        raise AssertionError("非法 group 未拒绝")


def test_api_returns_group(client, env):
    _sync(env, 'tasks:\n  - id: t4\n    name: x\n    group: ai\n    command: python t.py\n')
    r = client.get("/api/tasks")
    body = r.json()
    row = next(t for t in body["tasks"] if t["id"] == "t4")
    assert row["group"] == "ai"


def test_profile_explicit_env_wins(client, env):
    """env 显式 HERMES_PROFILE 优先于 env_file 推导。"""
    _sync(env,
          'tasks:\n'
          '  - id: p1\n    name: x\n    group: ai\n    command: python hermes_trigger.py\n'
          '    env:\n      HERMES_PROFILE: "ohyes768"\n'
          '    env_file: /workspace/stock-info-dingding/.env.hermes-default\n')
    row = next(t for t in client.get("/api/tasks").json()["tasks"] if t["id"] == "p1")
    assert row["profile"] == "ohyes768"


def test_profile_default_env_file(client, env):
    """gw-8642.env → default profile；gw-8643.env → ohyes768。

    2026-11-07 起 AI 任务凭证迁到 ~/.hermes/gw-*.env（不再挂 stock-info checkout）；
    旧 stock-info 路径不再对应任何 profile，推导为 None（防误绑）。"""
    _sync(env,
          'tasks:\n'
          '  - id: p2\n    name: x\n    group: ai\n    command: python hermes_trigger.py\n'
          '    env_file: /hermes-home/gw-8642.env\n'
          '  - id: p3\n    name: y\n    group: ai\n    command: python hermes_trigger.py\n'
          '    env_file: /hermes-home/gw-8643.env\n'
          '  - id: p3b\n    name: z\n    group: ai\n    command: python hermes_trigger.py\n'
          '    env_file: /workspace/stock-info-dingding/.env.hermes-default\n')
    rows = {t["id"]: t["profile"] for t in client.get("/api/tasks").json()["tasks"]}
    assert rows["p2"] == "default"
    assert rows["p3"] == "ohyes768"
    assert rows["p3b"] is None


def test_profile_script_task_none(client, env):
    """脚本任务无 profile；未配 env_file 的 AI 任务也为 None。"""
    _sync(env,
          'tasks:\n'
          '  - id: p4\n    name: x\n    command: echo hi\n'
          '  - id: p5\n    name: y\n    group: ai\n    command: python t.py\n')
    rows = {t["id"]: t["profile"] for t in client.get("/api/tasks").json()["tasks"]}
    assert rows["p4"] is None
    assert rows["p5"] is None

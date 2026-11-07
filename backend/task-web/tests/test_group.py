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
        _sync(env, 'tasks:\n  - id: t3\n    name: x\n    group: ai\n    command: x\n')
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

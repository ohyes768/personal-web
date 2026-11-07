"""targets 输出目的（多选 dingtalk/wechat/rss）：登记校验与 API 透出。"""
from __future__ import annotations

from pathlib import Path

from src import db, registry


def _sync(env, text):
    Path(env["tasks_yaml"]).write_text(text, encoding="utf-8")
    return registry.sync_registry()


def test_targets_stored_multi(client, env):
    _sync(env, 'tasks:\n  - id: t1\n    name: x\n    command: echo hi\n'
               '    targets: [rss, dingtalk]\n')
    from src import db

    assert db.get_task("t1")["targets"] == '["rss", "dingtalk"]'


def test_targets_default_empty(client, env):
    _sync(env, 'tasks:\n  - id: t2\n    name: x\n    command: echo hi\n')
    from src import db

    assert db.get_task("t2")["targets"] == '[]'


def test_targets_invalid_rejected(client, env):
    try:
        _sync(env, 'tasks:\n  - id: t3\n    name: x\n    command: x\n'
                   '    targets: [email]\n')
    except ValueError as e:
        assert "targets 非法" in str(e)
    else:
        raise AssertionError("非法 targets 未拒绝")


def test_targets_api_returns(client, env):
    _sync(env, 'tasks:\n  - id: t4\n    name: x\n    command: python t.py\n'
               '    targets: [wechat]\n')
    row = next(t for t in client.get("/api/tasks").json()["tasks"] if t["id"] == "t4")
    assert row["targets"] == ["wechat"]

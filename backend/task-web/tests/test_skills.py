"""skills（AI 任务涉及的 skill 名）：登记校验与 API 透出。

tasks.yaml 是唯一来源：AI 任务写 skills: [gold-price-brief]，纯 prompt 驱动的任务不写。
页面「涉及 Skill」列只做展示，不参与调度。
"""
from __future__ import annotations

from pathlib import Path

from src import db, registry


def _sync(env, text):
    Path(env["tasks_yaml"]).write_text(text, encoding="utf-8")
    return registry.sync_registry()


def test_skills_stored_multi(client, env):
    _sync(env, 'tasks:\n  - id: s1\n    name: x\n    group: ai\n    command: python t.py\n'
               '    skills: [gold-price-brief, dingtalk-push]\n')
    assert db.get_task("s1")["skills"] == '["gold-price-brief", "dingtalk-push"]'


def test_skills_default_empty(client, env):
    """纯 prompt 驱动的 AI 任务（skill=None）不写该字段 → 空。"""
    _sync(env, 'tasks:\n  - id: s2\n    name: x\n    group: ai\n    command: python t.py\n')
    assert db.get_task("s2")["skills"] is None


def test_skills_comma_string(client, env):
    """也接受逗号分隔字符串写法。"""
    _sync(env, 'tasks:\n  - id: s3\n    name: x\n    group: ai\n    command: python t.py\n'
               '    skills: "hk-ipo-research, rss-relay-publish"\n')
    assert db.get_task("s3")["skills"] == '["hk-ipo-research", "rss-relay-publish"]'


def test_skills_invalid_rejected(client, env):
    """带空格/中文说明文字的条目直接拒绝，避免页面出现对不上 skill 目录的名字。"""
    for bad in ('skills: ["gold price brief"]\n', 'skills: [黄金研判]\n'):
        try:
            _sync(env, 'tasks:\n  - id: s4\n    name: x\n    group: ai\n    command: python t.py\n    ' + bad)
        except ValueError as e:
            assert "skills 条目非法" in str(e)
        else:
            raise AssertionError(f"非法 skills 未拒绝: {bad!r}")


def test_skills_api_returns(client, env):
    _sync(env, 'tasks:\n  - id: s5\n    name: x\n    group: ai\n    command: python t.py\n'
               '    skills: [natgeo-daily]\n'
               '  - id: s6\n    name: y\n    command: echo hi\n')
    rows = {t["id"]: t["skills"] for t in client.get("/api/tasks").json()["tasks"]}
    assert rows["s5"] == ["natgeo-daily"]
    assert rows["s6"] == []

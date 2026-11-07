"""生效 Hermes profile 可设置（11-07-profile-override）：页面覆盖、执行期应用、jobs.json 同源。

覆盖值存 `task_overrides`（tasks.yaml 每次同步都 upsert tasks 表，可编辑项必须分表），
执行时同时切三件事：凭证 env_file、HERMES_PROFILE、jobs.json 挂载宿主源。
"""
from __future__ import annotations

import json
from pathlib import Path

from src import db, executor, profiles, registry

AI_YAML = (
    "tasks:\n"
    "  - id: p1\n"
    "    name: ai 任务\n"
    "    group: ai\n"
    "    command: python hermes_trigger.py --jobs-json /hermes-cron/jobs.json\n"
    "    env_file: /hermes-home/gw-8642.env\n"
    "    volumes:\n"
    "      - /home/ohyes768/.hermes/cron:/hermes-cron:ro\n"
    "      - /home/ohyes768/ack:/ack:rw\n"
)


def _sync(env, yaml_text: str):
    Path(env["tasks_yaml"]).write_text(yaml_text, encoding="utf-8")
    return registry.sync_registry()


def _row(client, task_id: str) -> dict:
    return next(t for t in client.get("/api/tasks").json()["tasks"] if t["id"] == task_id)


# ---------------------------------------------------------------------------
# API：设置 / 清除覆盖
# ---------------------------------------------------------------------------

def test_profiles_endpoint_lists_catalog(client):
    r = client.get("/api/profiles")
    assert r.status_code == 200
    items = {p["name"]: p for p in r.json()["profiles"]}
    assert {"default", "ohyes768"} <= set(items)
    for p in items.values():
        assert p["env_file"] and p["jobs_dir"] and p["label"]
        assert isinstance(p["tasks"], int)


def test_override_wins_over_registry(client, env):
    _sync(env, AI_YAML)
    assert _row(client, "p1")["profile"] == "default"
    assert _row(client, "p1")["profile_source"] == "registry"

    r = client.put("/api/tasks/p1/profile", json={"profile": "ohyes768"})
    assert r.status_code == 200
    body = r.json()
    assert body["profile"] == "ohyes768"
    assert body["profile_source"] == "override"
    # 列表接口同样反映覆盖值（页面 5s 轮询靠它）
    assert _row(client, "p1")["profile"] == "ohyes768"
    assert db.get_profile_override("p1") == "ohyes768"


def test_override_survives_registry_resync(client, env):
    """yaml 重新同步不许冲掉用户设置。"""
    _sync(env, AI_YAML)
    client.put("/api/tasks/p1/profile", json={"profile": "ohyes768"})
    _sync(env, AI_YAML)
    assert _row(client, "p1")["profile"] == "ohyes768"
    assert _row(client, "p1")["profile_source"] == "override"


def test_override_clear_back_to_registry(client, env):
    _sync(env, AI_YAML)
    client.put("/api/tasks/p1/profile", json={"profile": "ohyes768"})
    r = client.put("/api/tasks/p1/profile", json={"profile": None})
    assert r.status_code == 200
    assert r.json()["profile"] == "default"
    assert r.json()["profile_source"] == "registry"
    assert db.get_profile_override("p1") is None


def test_override_rejects_unknown_profile(client, env):
    _sync(env, AI_YAML)
    r = client.put("/api/tasks/p1/profile", json={"profile": "nope"})
    assert r.status_code == 400
    assert "未知 profile" in r.json()["detail"]


def test_override_rejects_script_task(client, env):
    _sync(env, AI_YAML + "  - id: s1\n    name: 脚本任务\n    command: echo hi\n")
    r = client.put("/api/tasks/s1/profile", json={"profile": "ohyes768"})
    assert r.status_code == 400
    assert "只有 AI 任务" in r.json()["detail"]


def test_override_task_missing(client, env):
    _sync(env, AI_YAML)
    assert client.put("/api/tasks/zzz/profile", json={"profile": "default"}).status_code == 404


def test_delete_task_drops_override(env):
    _sync(env, AI_YAML)
    db.set_profile_override("p1", "ohyes768")
    db.delete_task("p1")
    assert db.get_profile_override("p1") is None


# ---------------------------------------------------------------------------
# 推导规则（纯函数）
# ---------------------------------------------------------------------------

def test_registered_profile_derivation():
    base = {"group_name": "ai"}
    assert profiles.registered_profile({**base, "env_file": "/hermes-home/gw-8642.env"}) == "default"
    assert profiles.registered_profile({**base, "env_file": "/hermes-home/gw-8643.env"}) == "ohyes768"
    assert profiles.registered_profile(
        {**base, "env_file": "/hermes-home/gw-8642.env", "env": json.dumps({"HERMES_PROFILE": "ohyes768"})}
    ) == "ohyes768"
    assert profiles.registered_profile({**base}) is None
    # 旧路径（stock-info checkout）在新目录里无对应 profile → None（不误绑）
    assert profiles.registered_profile({**base, "env_file": "/w/.env.hermes-default"}) is None
    assert profiles.registered_profile({"group_name": "script", "env_file": "/hermes-home/gw-8643.env"}) is None


def test_unknown_override_ignored_for_display():
    task = {"id": "x", "group_name": "ai", "env_file": "/hermes-home/gw-8643.env"}
    assert profiles.effective_profile(task, "ghost") == "ohyes768"
    assert profiles.profile_source(task, "ghost") == "registry"


# ---------------------------------------------------------------------------
# 执行期应用：env_file + HERMES_PROFILE
# ---------------------------------------------------------------------------

def _catalog(monkeypatch, tmp_path):
    default_env = tmp_path / ".env.hermes-default"
    default_env.write_text("BASE_URL=http://gw:8642\nAPI_KEY=key-default\n", encoding="utf-8")
    ohyes_env = tmp_path / ".env"
    ohyes_env.write_text("BASE_URL=http://gw:8643\nAPI_KEY=key-ohyes\n", encoding="utf-8")
    monkeypatch.setenv("TASK_WEB_HERMES_PROFILES", json.dumps({
        "default": {"env_file": str(default_env), "jobs_dir": "/h/default/cron"},
        "ohyes768": {"env_file": str(ohyes_env), "jobs_dir": "/h/ohyes768/cron"},
    }))
    return default_env, ohyes_env


def test_prompt_injected_as_env(client, env, tmp_path, monkeypatch):
    """登记 prompt → 执行环境注入 HERMES_PROMPT，优先于 jobs.json 回退。"""
    _catalog(monkeypatch, tmp_path)
    _sync(env,
          "tasks:\n"
          "  - id: p4\n    name: ai\n    group: ai\n    command: python hermes_trigger.py --job-id x\n"
          "    prompt: |-\n"
          "      第一行\n"
          "      第二行\n")
    e = executor._task_env(db.get_task("p4"))
    assert e["HERMES_PROMPT"] == "第一行\n第二行"


def test_no_prompt_no_env(client, env, tmp_path, monkeypatch):
    _catalog(monkeypatch, tmp_path)
    _sync(env,
          "tasks:\n"
          "  - id: p5\n    name: ai\n    group: ai\n    command: python hermes_trigger.py\n")
    e = executor._task_env(db.get_task("p5"))
    assert "HERMES_PROMPT" not in e


def test_task_env_uses_profile_credentials(client, env, tmp_path, monkeypatch):
    default_env, _ = _catalog(monkeypatch, tmp_path)
    _sync(env,
          "tasks:\n"
          "  - id: p2\n    name: ai\n    group: ai\n    command: python t.py\n"
          f"    env_file: {default_env}\n"
          "    env:\n"
          "      HERMES_PROFILE: default\n"
          "      KEEP: '1'\n")
    task = db.get_task("p2")
    # 未设置覆盖：登记推导 = default，凭证取 default 的 env_file
    e = executor._task_env(task)
    assert e["BASE_URL"] == "http://gw:8642"
    assert e["API_KEY"] == "key-default"
    assert e["HERMES_PROFILE"] == "default"

    db.set_profile_override("p2", "ohyes768")
    e = executor._task_env(db.get_task("p2"))
    assert e["BASE_URL"] == "http://gw:8643"          # 网关随 profile 切换
    assert e["API_KEY"] == "key-ohyes"                # 凭证随 profile 切换
    assert e["HERMES_PROFILE"] == "ohyes768"          # yaml 里写死的旧值被覆盖
    assert e["KEEP"] == "1"                           # 其余登记变量保留


def test_jobs_mount_follows_profile(client, env, tmp_path, monkeypatch):
    default_env, _ = _catalog(monkeypatch, tmp_path)
    _sync(env,
          "tasks:\n"
          "  - id: p3\n    name: ai\n    group: ai\n    command: python hermes_trigger.py --jobs-json /hermes-cron/jobs.json\n"
          f"    env_file: {default_env}\n"
          "    volumes:\n"
          "      - /h/default/cron:/hermes-cron:ro\n"
          "      - /home/ohyes768/ack:/ack:rw\n")
    vol = executor._task_volumes(db.get_task("p3"))
    assert vol == {
        "/h/default/cron": {"bind": "/hermes-cron", "mode": "ro"},
        "/home/ohyes768/ack": {"bind": "/ack", "mode": "rw"},
    }

    db.set_profile_override("p3", "ohyes768")
    vol = executor._task_volumes(db.get_task("p3"))
    # 宿主源换成生效 profile 的 cron 目录，容器路径不变 → 命令里的 --jobs-json 照旧有效
    assert vol["/h/ohyes768/cron"] == {"bind": "/hermes-cron", "mode": "ro"}
    assert "/h/default/cron" not in vol
    assert vol["/home/ohyes768/ack"] == {"bind": "/ack", "mode": "rw"}


def test_apply_jobs_mount_ignores_non_jobs_volumes():
    # 默认目录：default → ~/.hermes/cron，ohyes768 → ~/.hermes/profiles/ohyes768/cron
    specs = ["/data/x:/x", "/home/ohyes768/.hermes/profiles/ohyes768/cron:/hermes-cron-p7:ro"]
    out = profiles.apply_jobs_mount(specs, "default")
    assert out == ["/data/x:/x", "/home/ohyes768/.hermes/cron:/hermes-cron-p7:ro"]
    assert profiles.apply_jobs_mount(specs, None) == specs

"""Pack API boundary tests with existing offline Git fixtures."""
import time
import pytest
from tests.test_api import client, roots, env, source_repo, upstream_repo, CANONICAL_URL, PASSWORD


def await_pack_task(client, task_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/github-packs/tasks/{task_id}")
        assert response.status_code == 200, response.text
        task = response.json()
        if task["state"] != "running":
            return task
        time.sleep(0.05)
    raise AssertionError("pack task timed out")


def test_pack_add_uses_one_repository_and_no_child_registration(client, roots):
    created = client.post("/api/github-packs", json={"repository": CANONICAL_URL, "password": PASSWORD})
    assert created.status_code == 202, created.text
    task = await_pack_task(client, created.json()["task_id"])
    assert task["state"] == "done", task
    packs = client.get("/api/github-packs").json()["items"]
    assert len(packs) == 1 and packs[0]["skill_count"] == 2
    assert not (roots.github_cache / "staging").exists()
    assert all(item["source"] == "local" for item in client.get("/api/skills").json()["items"])
    repeat = client.post("/api/github-packs", json={"repository": CANONICAL_URL + ".git", "password": PASSWORD})
    assert repeat.status_code == 202
    assert await_pack_task(client, repeat.json()["task_id"])["state"] == "done"
    assert len(client.get("/api/github-packs").json()["items"]) == 1


def test_pack_write_password_checked_before_any_git(client, roots):
    response = client.post("/api/github-packs", json={"repository": CANONICAL_URL, "password": "bad"})
    assert response.status_code == 401
    assert not (roots.github_cache / "repos").exists()
    assert client.get("/api/github-packs/tasks/unknown").status_code == 404


def test_pack_rejects_export_target_and_path_injection(client):
    created = client.post("/api/github-packs", json={"repository": CANONICAL_URL, "password": PASSWORD})
    assert created.status_code == 202
    task = await_pack_task(client, created.json()["task_id"])
    pack_id = task["result"]["pack"]["id"]
    assert client.post(f"/api/github-packs/{pack_id}/install",
        json={"password": PASSWORD, "targets": ["windows-codex"]}).status_code == 400
    assert client.post("/api/github-packs",
        json={"password": PASSWORD, "repository": "file:///etc"}).status_code == 400
    assert client.post("/api/github-packs",
        json={"password": PASSWORD, "repository": CANONICAL_URL, "path": "/etc"}).status_code == 400


def test_legacy_skill_cannot_recheckout_or_delete_pack_repository(client):
    from src.config import Settings
    from src.db import SkillStateStore
    from src.models import RegistrySkill
    store = SkillStateStore.from_settings(Settings())
    store.upsert_registry_skill(RegistrySkill(id="old-alpha",name="alpha",source="github",
        repository=CANONICAL_URL,path="skills/alpha"))
    assert client.get("/api/github-packs").status_code == 200
    response = client.post("/api/skills/github/old-alpha/clone",json={"password":PASSWORD})
    assert response.status_code == 409 and response.json()["code"] == "pack_managed"
    response = client.request("DELETE","/api/skills/old-alpha",json={"password":PASSWORD})
    assert response.status_code == 409 and response.json()["code"] == "pack_managed"
    plan = client.post("/api/skills/publish/plan",
        json={"items":[{"skill_id":"old-alpha","targets":["hermes"]}]})
    assert plan.status_code == 200 and plan.json()["items"][0]["action"] == "blocked"


def test_boot_preserves_legacy_checkout_before_pack_conversion(env, source_repo, roots):
    from fastapi.testclient import TestClient
    from src.main import app
    from src.config import Settings
    from src.db import SkillStateStore
    from src.models import RegistrySkill
    from tests.test_api import run_git
    old = roots.github_cache / "old-alpha"
    old.mkdir()
    run_git("init", str(old))
    (old / "SKILL.md").write_text("---\nname: alpha\n---\n")
    store = SkillStateStore.from_settings(Settings())
    store.upsert_registry_skill(RegistrySkill(id="old-alpha",name="alpha",source="github",
        repository=CANONICAL_URL,path="."))
    with TestClient(app) as test_client:
        assert test_client.get("/api/health").status_code == 200
        assert old.is_dir(), "startup moved a checkout still used by legacy installation"
        assert not (roots.github_cache / "repos/example__two-skills").exists()

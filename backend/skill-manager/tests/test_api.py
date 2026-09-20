"""API 层测试（design 7 / Task 5）：公开只读端点、密码守卫、发布计划
无副作用、批量逐项结果与错误契约。

fixture 环境：tmp_path 构造全部受控根目录 + registry.json 写入 local
skill 条目 + 本地 bare 仓库经 remotes 映射充当 GitHub 远端（离线）。
依赖真实 symlink 的测试标 `requires_symlink`（conftest 在无特权时跳过）。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_git_cache
from src.config import Settings
from src.db import SkillStateStore
from src.services.git_cache import GitCacheService

PASSWORD = "test-password"
CANONICAL_URL = "https://github.com/example/two-skills"

LOCAL_REGISTRY = {
    "version": "1.0",
    "updated": "",
    "skills": [
        {
            "id": "alpha",
            "name": "Alpha",
            "source": "local",
            "path": "alpha",
            "tags": ["demo"],
            "summary": "本地示例技能",
        }
    ],
    "agents": {},
}


def run_git(*argv: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ["git", *argv],
        cwd=cwd,
        shell=False,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


@pytest.fixture()
def roots(tmp_path):
    source_root = tmp_path / "source"
    github_cache = tmp_path / "cache"
    state = tmp_path / "state"
    targets = tmp_path / "targets"
    openclaw = targets / "openclaw"
    hermes = targets / "hermes"
    for directory in (source_root, github_cache, state, openclaw, hermes):
        directory.mkdir(parents=True)
    return SimpleNamespace(
        source_root=source_root,
        github_cache=github_cache,
        state=state,
        targets=targets,
        openclaw=openclaw,
        hermes=hermes,
    )


@pytest.fixture()
def env(roots, monkeypatch):
    monkeypatch.setenv("SKILLS_SOURCE_ROOT", str(roots.source_root))
    monkeypatch.setenv("GITHUB_SKILL_CACHE_ROOT", str(roots.github_cache))
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", str(roots.openclaw))
    monkeypatch.setenv("HERMES_SKILLS_ROOT", str(roots.hermes))
    monkeypatch.setenv("SKILL_MANAGER_STATE_DIR", str(roots.state))
    monkeypatch.setenv("SKILL_MANAGER_TARGETS_MOUNT_ROOT", str(roots.targets))
    monkeypatch.setenv("SKILL_MANAGER_ADMIN_PASSWORD", PASSWORD)


@pytest.fixture()
def source_repo(roots):
    """源库内容：local skill `alpha` + registry.json。"""
    skill_dir = roots.source_root / "alpha"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: alpha\n---\n", encoding="utf-8")
    (roots.source_root / "registry.json").write_text(
        json.dumps(LOCAL_REGISTRY, ensure_ascii=False), encoding="utf-8"
    )


@pytest.fixture()
def upstream_repo(tmp_path):
    """本地 bare 仓库充当 GitHub 远端（两个 skill 目录）。"""
    work = tmp_path / "upstream-work"
    work.mkdir()
    run_git("init", str(work))
    run_git("config", "user.email", "fixture@example.com", cwd=work)
    run_git("config", "user.name", "Fixture", cwd=work)
    for rel in ("skills/alpha", "skills/beta"):
        (work / rel).mkdir(parents=True)
        (work / rel / "SKILL.md").write_text(f"---\nname: {rel}\n---\n", encoding="utf-8")
    run_git("add", "-A", cwd=work)
    run_git("commit", "-m", "fixture: two skills", cwd=work)

    bare = tmp_path / "upstream.git"
    run_git("clone", "--bare", str(work), str(bare))
    revision = run_git("rev-parse", "HEAD", cwd=bare).strip()
    return SimpleNamespace(bare=bare, revision=revision)


@pytest.fixture()
def client(env, source_repo, upstream_repo):
    from src.main import app

    with TestClient(app) as test_client:
        settings = Settings()
        store = SkillStateStore.from_settings(settings)
        app.dependency_overrides[get_git_cache] = lambda: GitCacheService(
            settings,
            store,
            remotes={CANONICAL_URL: str(upstream_repo.bare)},
        )
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def publish_request():
    return {
        "password": PASSWORD,
        "items": [{"skill_id": "alpha", "targets": ["openclaw"]}],
    }


@pytest.fixture()
def plan_request():
    return {"items": [{"skill_id": "alpha", "targets": ["openclaw"]}]}


# ---------- implement.md 给定用例 ----------


def test_list_skills_is_public(client):
    response = client.get("/api/skills")

    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    alpha = next(card for card in items if card["id"] == "alpha")
    assert alpha["source"] == "local"
    assert alpha["tags"] == ["demo"]


def test_publish_requires_correct_password(client, publish_request):
    wrong = client.post(
        "/api/skills/publish", json={**publish_request, "password": "wrong"}
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "invalid_password"

    ok = client.post("/api/skills/publish", json=publish_request)
    assert ok.status_code == 200
    assert [item["skill_id"] for item in ok.json()["items"]] == ["alpha"]


def test_plan_does_not_mutate_links(client, plan_request, roots):
    response = client.post("/api/skills/publish/plan", json=plan_request)

    assert response.status_code == 200
    assert response.json()["items"][0]["action"] == "add"
    assert not any(roots.openclaw.iterdir())


# ---------- 公开端点与错误契约 ----------


def test_scan_is_public_and_rejects_invalid_urls(client):
    ok = client.post("/api/skills/github/scan", json={"repository": CANONICAL_URL})
    assert ok.status_code == 200
    assert [c["path"] for c in ok.json()["candidates"]] == [
        "skills/alpha",
        "skills/beta",
    ]

    for url in ("file:///tmp/skill", "https://gitlab.com/a/b", "not a url"):
        bad = client.post("/api/skills/github/scan", json={"repository": url})
        assert bad.status_code == 400, url
        assert bad.json()["code"] == "invalid_repository"


def test_wrong_password_leaves_filesystem_unchanged(client, publish_request, roots):
    before = sorted(str(p) for p in roots.openclaw.iterdir())

    response = client.post(
        "/api/skills/publish", json={**publish_request, "password": "nope"}
    )

    assert response.status_code == 401
    after = sorted(str(p) for p in roots.openclaw.iterdir())
    assert before == after


def test_unknown_skill_returns_404(client):
    plan = client.post(
        "/api/skills/publish/plan",
        json={"items": [{"skill_id": "ghost", "targets": ["openclaw"]}]},
    )
    assert plan.status_code == 404
    assert plan.json()["code"] == "skill_not_found"

    rollback = client.post(
        "/api/skills/ghost/targets/openclaw/rollback", json={"password": PASSWORD}
    )
    assert rollback.status_code == 404

    unpublish = client.request(
        "DELETE", "/api/skills/ghost/targets/openclaw", json={"password": PASSWORD}
    )
    assert unpublish.status_code == 404


def test_invalid_skill_id_and_target_return_400(client):
    bad_id = client.post(
        "/api/skills/publish/plan",
        json={"items": [{"skill_id": "BAD_ID", "targets": ["openclaw"]}]},
    )
    assert bad_id.status_code == 400

    bad_target = client.post(
        "/api/skills/publish/plan",
        json={"items": [{"skill_id": "alpha", "targets": ["slack"]}]},
    )
    assert bad_target.status_code == 400

    bad_path = client.post("/api/skills/BAD/targets/openclaw/rollback", json={"password": PASSWORD})
    assert bad_path.status_code == 400


def test_rollback_without_snapshot_returns_409(client):
    response = client.post(
        "/api/skills/alpha/targets/openclaw/rollback", json={"password": PASSWORD}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "rollback_unavailable"


# ---------- 需要真实 symlink 的发布/下架/回滚 ----------


@pytest.mark.requires_symlink
def test_publish_creates_symlink_in_target_root(client, publish_request, roots):
    response = client.post("/api/skills/publish", json=publish_request)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["status"] == "success"
    assert item["action"] == "add"
    link = roots.openclaw / "alpha"
    assert link.is_symlink()
    assert link.resolve() == (roots.source_root / "alpha").resolve()


@pytest.mark.requires_symlink
def test_batch_keeps_successful_item_when_another_target_is_blocked(
    client, publish_request, roots
):
    (roots.hermes / "alpha").mkdir()

    response = client.post(
        "/api/skills/publish",
        json={
            "password": PASSWORD,
            "items": [{"skill_id": "alpha", "targets": ["openclaw", "hermes"]}],
        },
    )

    assert response.status_code == 200
    statuses = {
        item["target"]: item["status"] for item in response.json()["items"]
    }
    assert statuses == {"openclaw": "success", "hermes": "blocked"}
    assert (roots.openclaw / "alpha").is_symlink()


@pytest.mark.requires_symlink
def test_unpublish_requires_password_then_removes_only_the_link(
    client, publish_request, roots
):
    client.post("/api/skills/publish", json=publish_request)

    denied = client.request(
        "DELETE", "/api/skills/alpha/targets/openclaw", json={"password": "wrong"}
    )
    assert denied.status_code == 401
    assert (roots.openclaw / "alpha").is_symlink()

    ok = client.request(
        "DELETE", "/api/skills/alpha/targets/openclaw", json={"password": PASSWORD}
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "removed"
    assert not (roots.openclaw / "alpha").exists()


@pytest.mark.requires_symlink
def test_rollback_restores_previous_link(client, publish_request, roots):
    client.post("/api/skills/publish", json=publish_request)
    # 第二次发布前制造一个可回滚来源：把 alpha 换成不同内容目录再发布
    v2 = roots.source_root / "alpha-v2"
    v2.mkdir()
    (v2 / "SKILL.md").write_text("---\nname: alpha-v2\n---\n", encoding="utf-8")
    registry = json.loads(
        (roots.source_root / "registry.json").read_text(encoding="utf-8")
    )
    registry["skills"][0]["path"] = "alpha-v2"
    (roots.source_root / "registry.json").write_text(
        json.dumps(registry, ensure_ascii=False), encoding="utf-8"
    )
    client.post("/api/skills/publish", json=publish_request)

    response = client.post(
        "/api/skills/alpha/targets/openclaw/rollback", json={"password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["action"] == "rollback"
    assert (roots.openclaw / "alpha").resolve() == (
        roots.source_root / "alpha"
    ).resolve()


# ---------- GitHub 登记与更新检查 ----------


def _register_payload(password: str = PASSWORD) -> dict:
    return {
        "password": password,
        "repository": CANONICAL_URL,
        "path": "skills/alpha",
        "name": "Fixture",
        "tags": ["test"],
        "summary": "登记测试",
    }


def test_register_github_skill_requires_password_and_persists(client, roots):
    before = (roots.source_root / "registry.json").read_text(encoding="utf-8")

    denied = client.post("/api/skills/github", json=_register_payload("wrong"))
    assert denied.status_code == 401
    assert (
        (roots.source_root / "registry.json").read_text(encoding="utf-8") == before
    )
    assert not any(roots.github_cache.iterdir())

    ok = client.post("/api/skills/github", json=_register_payload())
    assert ok.status_code == 200
    card = ok.json()
    assert card["source"] == "github"
    assert card["name"] == "Fixture"
    assert card["tags"] == ["test"]

    registry_data = json.loads(
        (roots.source_root / "registry.json").read_text(encoding="utf-8")
    )
    assert any(s["id"] == card["id"] for s in registry_data["skills"])
    assert (roots.github_cache / card["id"] / "skills" / "alpha" / "SKILL.md").is_file()


def test_register_github_skill_rejects_invalid_repository(client, roots):
    response = client.post(
        "/api/skills/github",
        json={**_register_payload(), "repository": "https://gitlab.com/a/b"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_repository"
    assert not any(roots.github_cache.iterdir())


def test_check_updates_reports_versions_without_publishing(client, roots):
    registered = client.post("/api/skills/github", json=_register_payload()).json()

    response = client.post("/api/skills/check-updates", json={})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["skill_id"] for item in items] == [registered["id"]]
    info = items[0]["info"]
    assert items[0]["result"] == "ok"
    assert info["remote_revision"]
    assert info["cached_revision"] == info["remote_revision"]
    assert info["has_update"] is False
    # 检查动作绝不发布：目标根保持为空
    assert not any(roots.openclaw.iterdir())
    assert not any(roots.hermes.iterdir())


def test_check_updates_is_public_and_reports_unknown_ids(client):
    response = client.post("/api/skills/check-updates", json={"skill_ids": ["ghost"]})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["skill_id"] for item in items] == ["ghost"]
    assert items[0]["result"] == "error"

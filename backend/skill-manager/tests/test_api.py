"""API 层测试（design 7 / Task 5）：公开只读端点、密码守卫、发布计划
无副作用、批量逐项结果与错误契约。

fixture 环境：tmp_path 构造全部受控根目录 + 源库 local skill 目录
（首次 /api/skills 对账自动登记 SQLite）+ 本地 bare 仓库经 remotes
映射充当 GitHub 远端（离线）。登记/删除断言 DB 状态变化。
依赖真实 symlink 的测试标 `requires_symlink`（conftest 在无特权时跳过）。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_git_cache
from src.config import Settings
from src.db import (
    DeploymentRecord,
    GithubCheckRecord,
    SkillStateStore,
)
from src.models import RegistrySkill
from src.services.git_cache import GitCacheService
from src.services.registry import RegistryService

PASSWORD = "test-password"
CANONICAL_URL = "https://github.com/example/two-skills"


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
    """源库内容：local skill `alpha` 目录（首次列表对账自动登记）。"""
    skill_dir = roots.source_root / "alpha"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: alpha\n---\n", encoding="utf-8")


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
        # 预热：首次列表触发对账，登记源库自研 skill（替代原 registry.json 导入）
        test_client.get("/api/skills")
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
    # alpha 由源库对账自动登记（frontmatter 无 tags/description）
    assert alpha["tags"] == []
    assert alpha["source_missing"] is False


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


# ---------- 需要真实 symlink 的发布/下架 ----------


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
    denied = client.post("/api/skills/github", json=_register_payload("wrong"))
    assert denied.status_code == 401
    assert not any(roots.github_cache.iterdir())

    ok = client.post("/api/skills/github", json=_register_payload())
    assert ok.status_code == 200
    card = ok.json()
    assert card["source"] == "github"
    assert card["name"] == "Fixture"
    assert card["tags"] == ["test"]

    # 登记真源是 SQLite：新条目入库且列表可见
    store = SkillStateStore.from_settings(Settings())
    registry = RegistryService(store, roots.source_root)
    assert registry.get(card["id"]) is not None
    card_ids = [c["id"] for c in client.get("/api/skills").json()["items"]]
    assert card["id"] in card_ids
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


@pytest.mark.requires_symlink
def test_publish_fetches_recorded_remote_revision_before_linking(
    client, roots, upstream_repo, tmp_path
):
    """R3 / design 5：缓存更新仅随管理员确认的发布执行——检查发现远端
    更新后，发布动作把缓存 fetch/checkout 到受记录 revision，再创建链接。"""
    registered = client.post("/api/skills/github", json=_register_payload()).json()
    skill_id = registered["id"]
    v1 = upstream_repo.revision

    # 远端前进一个 commit：只改 skills/alpha 的 SKILL.md
    work = tmp_path / "push-work"
    run_git("clone", str(upstream_repo.bare), str(work))
    run_git("config", "user.email", "fixture@example.com", cwd=work)
    run_git("config", "user.name", "Fixture", cwd=work)
    (work / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha-v2\n---\n", encoding="utf-8"
    )
    run_git("commit", "-am", "fixture: alpha v2", cwd=work)
    run_git("push", cwd=work)
    v2 = run_git("rev-parse", "HEAD", cwd=work).strip()
    assert v2 != v1

    checked = client.post("/api/skills/check-updates", json={}).json()["items"][0]
    assert checked["result"] == "ok"
    assert checked["info"]["has_update"] is True
    assert checked["info"]["remote_revision"] == v2
    assert checked["info"]["cached_revision"] == v1

    # 计划展示的待发布版本 = 受记录的远端 revision
    plan = client.post(
        "/api/skills/publish/plan",
        json={"items": [{"skill_id": skill_id, "targets": ["openclaw"]}]},
    ).json()
    assert plan["items"][0]["action"] == "add"
    assert plan["items"][0]["planned_revision"] == v2

    published = client.post(
        "/api/skills/publish",
        json={
            "password": PASSWORD,
            "items": [{"skill_id": skill_id, "targets": ["openclaw"]}],
        },
    )
    assert published.status_code == 200
    assert published.json()["items"][0]["status"] == "success"

    # 缓存与目标链接都落在远端最新 revision
    skill_dir = (roots.github_cache / skill_id / "skills/alpha").resolve()
    assert "alpha-v2" in (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    link = roots.openclaw / skill_id
    assert link.is_symlink()
    assert link.resolve() == skill_dir
    card = next(
        item for item in client.get("/api/skills").json()["items"] if item["id"] == skill_id
    )
    assert card["deployments"]["openclaw"]["revision"] == v2


@pytest.mark.requires_symlink
def test_registered_github_skill_can_be_planned_and_published(client, roots):
    """Task 8 端到端：扫描 → 登记（密码）→ 计划 → 发布（密码）→ symlink 落地。"""
    scanned = client.post("/api/skills/github/scan", json={"repository": CANONICAL_URL})
    assert scanned.status_code == 200
    candidates = scanned.json()["candidates"]
    assert candidates

    registered = client.post(
        "/api/skills/github",
        json={
            "password": PASSWORD,
            "repository": CANONICAL_URL,
            "path": candidates[0]["path"],
            "name": "Fixture",
            "tags": ["test"],
        },
    )
    assert registered.status_code == 200
    skill_id = registered.json()["id"]

    plan = client.post(
        "/api/skills/publish/plan",
        json={"items": [{"skill_id": skill_id, "targets": ["openclaw"]}]},
    )
    assert plan.status_code == 200
    assert plan.json()["items"][0]["action"] == "add"

    published = client.post(
        "/api/skills/publish",
        json={
            "password": PASSWORD,
            "items": [{"skill_id": skill_id, "targets": ["openclaw"]}],
        },
    )
    assert published.status_code == 200
    assert published.json()["items"][0]["status"] == "success"
    link = roots.openclaw / skill_id
    assert link.is_symlink()
    assert link.resolve() == (roots.github_cache / skill_id / candidates[0]["path"]).resolve()


def test_check_updates_is_public_and_reports_unknown_ids(client):
    response = client.post("/api/skills/check-updates", json={"skill_ids": ["ghost"]})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["skill_id"] for item in items] == ["ghost"]
    assert items[0]["result"] == "error"


# ---------- 缓存缺失 Clone 端点 ----------


def _upsert_registry_entry(roots: SimpleNamespace, skill: dict) -> None:
    """直接向登记 DB upsert 条目（登记真源是 SQLite）。"""
    store = SkillStateStore.from_settings(Settings())
    RegistryService(store, roots.source_root).upsert(
        RegistrySkill.model_validate(skill)
    )


def _missing_cache_skill(repository: str) -> dict:
    return {
        "id": "two-skills",
        "name": "Two Skills",
        "source": "github",
        "path": "skills/alpha",
        "repository": repository,
    }


def test_clone_rebuilds_missing_cache_and_reports_revision(client, roots, upstream_repo):
    """缓存缺失的 GitHub skill：clone 重建缓存并返回检出 revision；local
    来源卡片恒不缺失。"""
    _upsert_registry_entry(roots, _missing_cache_skill(CANONICAL_URL))
    cards = {c["id"]: c for c in client.get("/api/skills").json()["items"]}
    assert cards["two-skills"]["cache_missing"] is True
    assert cards["alpha"]["cache_missing"] is False

    response = client.post(
        "/api/skills/github/two-skills/clone", json={"password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json() == {
        "skill_id": "two-skills",
        "revision": upstream_repo.revision,
    }
    assert (roots.github_cache / "two-skills" / "skills" / "alpha" / "SKILL.md").is_file()
    # clone 后卡片恢复可用
    cards = {c["id"]: c for c in client.get("/api/skills").json()["items"]}
    assert cards["two-skills"]["cache_missing"] is False


def test_clone_unknown_skill_returns_404(client):
    response = client.post(
        "/api/skills/github/ghost/clone", json={"password": PASSWORD}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "skill_not_found"


def test_clone_local_skill_returns_400(client):
    response = client.post(
        "/api/skills/github/alpha/clone", json={"password": PASSWORD}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_skill"


def test_clone_returns_400_when_remote_unreachable(client, roots, upstream_repo):
    """ls-remote 失败（远端映射指向不存在的本地 bare 仓库，离线快速失败）
    → 400 cache_failed，且缓存目录保持为空。"""
    from src.main import app

    _upsert_registry_entry(
        roots, _missing_cache_skill("https://github.com/example/missing")
    )
    settings = Settings()
    store = SkillStateStore.from_settings(settings)
    app.dependency_overrides[get_git_cache] = lambda: GitCacheService(
        settings,
        store,
        remotes={
            "https://github.com/example/missing": str(
                upstream_repo.bare.parent / "missing.git"
            )
        },
    )
    response = client.post(
        "/api/skills/github/two-skills/clone", json={"password": PASSWORD}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "cache_failed"
    assert not any(roots.github_cache.iterdir())


def test_clone_returns_400_when_git_binary_missing(client, roots, monkeypatch):
    """运行环境没有 git 二进制：FileNotFoundError 被包装为域错误 →
    400 cache_failed，而非未捕获异常的 500。"""
    import src.services.git_cache as git_cache_module

    def _raise_file_not_found(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(git_cache_module.subprocess, "run", _raise_file_not_found)
    _upsert_registry_entry(roots, _missing_cache_skill(CANONICAL_URL))
    response = client.post(
        "/api/skills/github/two-skills/clone", json={"password": PASSWORD}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "cache_failed"
    assert "git" in response.json()["message"]


def test_clone_requires_password(client, roots):
    _upsert_registry_entry(roots, _missing_cache_skill(CANONICAL_URL))

    denied = client.post(
        "/api/skills/github/two-skills/clone", json={"password": "wrong"}
    )

    assert denied.status_code == 401
    assert denied.json()["code"] == "invalid_password"
    assert not any(roots.github_cache.iterdir())


# ---------- 卡片账实核对（link_missing） ----------


def _insert_active_deployment(roots: SimpleNamespace, skill_id: str, target: str) -> None:
    """向账本直插一条 active 部署记录（不经发布流程，无需 symlink 特权）。"""
    store = SkillStateStore.from_settings(Settings())
    store.upsert_deployment(
        DeploymentRecord(
            skill_id=skill_id,
            target=target,
            source_revision="",
            source_path=str(roots.source_root / skill_id),
            current_link_target="",
            status="active",
            published_at="2026-09-21T00:00:00+00:00",
        )
    )


def test_list_flags_link_missing_for_active_deployment_without_link(client, roots):
    """账本 active 但目标链接不存在（如被手动删除）→ 卡片标记 link_missing。"""
    _insert_active_deployment(roots, "alpha", "hermes")

    cards = {c["id"]: c for c in client.get("/api/skills").json()["items"]}

    deployment = cards["alpha"]["deployments"]["hermes"]
    assert deployment["status"] == "active"
    assert deployment["link_missing"] is True
    # 未插记录的 target 不出现在卡片 deployments 里
    assert "openclaw" not in cards["alpha"]["deployments"]


@pytest.mark.requires_symlink
def test_list_reports_no_link_missing_when_active_link_exists(client, roots):
    """账本 active 且目标链接存在 → 不标记 link_missing（正常 emerald 徽章）。"""
    _insert_active_deployment(roots, "alpha", "hermes")
    os.symlink(
        roots.source_root / "alpha", roots.hermes / "alpha", target_is_directory=True
    )

    cards = {c["id"]: c for c in client.get("/api/skills").json()["items"]}

    assert cards["alpha"]["deployments"]["hermes"]["link_missing"] is False


# ---------- 删除已登记 GitHub Skill ----------


def _seed_deletable_github_skill(roots: SimpleNamespace) -> None:
    """登记一个 GitHub 条目；源库保持非 git 仓库（模拟 NAS git add 128 场景）。"""
    _upsert_registry_entry(roots, _missing_cache_skill(CANONICAL_URL))


def _seed_derived_state(skill_id: str) -> SkillStateStore:
    """写入 github_check，供删除清理断言。"""
    store = SkillStateStore.from_settings(Settings())
    store.upsert_github_check(
        GithubCheckRecord(
            skill_id=skill_id,
            repository=CANONICAL_URL,
            remote_revision="sha-r",
            remote_tags="",
            cached_revision="sha-r",
            result="ok",
            error=None,
            checked_at="2026-09-21T00:00:00+00:00",
        )
    )
    return store


def test_delete_github_skill_removes_registry_entry_and_derived_state(client, roots):
    """成功删除：DB 行移除且源库无需是 git 仓库（NAS git add 128 场景）；
    github_check 清理；缓存目录移除；列表不再显示。"""
    _seed_deletable_github_skill(roots)
    store = _seed_derived_state("two-skills")
    cache_dir = roots.github_cache / "two-skills" / ".git"
    cache_dir.mkdir(parents=True)
    assert not (roots.source_root / ".git").exists()

    response = client.request(
        "DELETE", "/api/skills/two-skills", json={"password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json() == {"skill_id": "two-skills"}
    registry = RegistryService(store, roots.source_root)
    assert registry.get("two-skills") is None
    assert store.get_github_check("two-skills") is None
    assert not (roots.github_cache / "two-skills").exists()
    card_ids = [c["id"] for c in client.get("/api/skills").json()["items"]]
    assert "two-skills" not in card_ids


def test_delete_github_skill_with_active_deployment_returns_409(client, roots):
    """任一 target 存在 active 部署 → 409，登记真源与派生数据均无变化。"""
    _seed_deletable_github_skill(roots)
    store = _seed_derived_state("two-skills")
    _insert_active_deployment(roots, "two-skills", "openclaw")

    response = client.request(
        "DELETE", "/api/skills/two-skills", json={"password": PASSWORD}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "skill_active"
    assert store.get_github_check("two-skills") is not None
    registry = RegistryService(store, roots.source_root)
    assert registry.get("two-skills") is not None


def test_register_and_delete_spawn_no_registry_git_processes(client, monkeypatch):
    """R2：登记/删除不再产生 git add/commit 子进程；删除流程全程零 git
    子进程（GitHub 缓存 clone/fetch 属 GitCacheService 职责，不在禁止范围）。"""
    calls: list[list[str]] = []
    real_run = subprocess.run

    def spy_run(cmd, *args, **kwargs):
        calls.append([str(part) for part in cmd])
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy_run)

    registered = client.post("/api/skills/github", json=_register_payload())
    assert registered.status_code == 200
    skill_id = registered.json()["id"]

    git_calls = [argv for argv in calls if argv and argv[0] == "git"]
    assert not any(argv[:2] == ["git", "add"] for argv in git_calls)
    assert not any(argv[:2] == ["git", "commit"] for argv in git_calls)

    calls.clear()
    deleted = client.request(
        "DELETE", f"/api/skills/{skill_id}", json={"password": PASSWORD}
    )
    assert deleted.status_code == 200
    assert [argv for argv in calls if argv and argv[0] == "git"] == []


def test_delete_local_skill_returns_400(client):
    response = client.request(
        "DELETE", "/api/skills/alpha", json={"password": PASSWORD}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "local_source"


def test_delete_unknown_skill_returns_404(client):
    response = client.request(
        "DELETE", "/api/skills/ghost", json={"password": PASSWORD}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "unknown_skill"


def test_delete_github_skill_requires_password(client, roots):
    _seed_deletable_github_skill(roots)

    response = client.request(
        "DELETE", "/api/skills/two-skills", json={"password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_password"

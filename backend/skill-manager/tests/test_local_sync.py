"""自研 skill 列表请求时对账（sync_local）测试。

覆盖：frontmatter 解析登记、无 frontmatter 降级、不覆盖人工维护条目、
源目录删除保留条目、github 条目不受影响，以及 API 层 source_missing 契约
与源库不可达降级（列表仍 200）。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.db import SkillStateStore
from src.models import RegistrySkill
from src.services.registry import RegistryService


@pytest.fixture()
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    return root


@pytest.fixture()
def store(tmp_path: Path) -> SkillStateStore:
    return SkillStateStore(tmp_path / "state" / "skill-manager.sqlite3")


@pytest.fixture()
def registry_service(store: SkillStateStore, source_root: Path) -> RegistryService:
    return RegistryService(store, source_root)


def make_skill(source_root: Path, dir_name: str, content: str = "---\nname: x\n---") -> None:
    skill_dir = source_root / dir_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


# ---------- sync_local：登记与降级 ----------


def test_sync_registers_new_local_skill_with_frontmatter(registry_service, store, source_root):
    make_skill(
        source_root,
        "new-skill",
        content="---\nname: 新技能\ndescription: 描述文本\n---",
    )

    assert registry_service.sync_local() == 1
    skill = store.get_registry_skill("new-skill")
    assert skill is not None
    assert skill.name == "新技能"
    assert skill.summary == "描述文本"
    # 幂等：二次对账无新增
    assert registry_service.sync_local() == 0


def test_sync_degrades_when_no_frontmatter(registry_service, store, source_root):
    make_skill(source_root, "plain", content="# no frontmatter\njust body")

    assert registry_service.sync_local() == 1
    skill = store.get_registry_skill("plain")
    assert skill is not None
    assert skill.name == "plain"
    assert skill.summary == ""


def test_sync_does_not_overwrite_manual_edits(registry_service, store, source_root):
    make_skill(source_root, "manual", content="---\nname: auto-name\n---")
    store.upsert_registry_skill(
        RegistrySkill(
            id="manual",
            name="人工名",
            source="local",
            path="manual",
            tags=["人工标签"],
            summary="人工描述",
            status="deprecated",
        )
    )

    assert registry_service.sync_local() == 0
    skill = store.get_registry_skill("manual")
    assert skill is not None
    assert skill.name == "人工名"
    assert skill.summary == "人工描述"
    assert skill.tags == ["人工标签"]
    assert skill.status == "deprecated"


def test_sync_keeps_entry_when_source_dir_deleted(registry_service, store, source_root):
    make_skill(source_root, "gone")
    assert registry_service.sync_local() == 1

    shutil.rmtree(source_root / "gone")

    assert registry_service.sync_local() == 0
    assert store.get_registry_skill("gone") is not None


def test_sync_ignores_github_skills(registry_service, store, source_root):
    make_skill(source_root, "local-one")
    store.upsert_registry_skill(
        RegistrySkill(
            id="gh",
            name="GH",
            source="github",
            path=".",
            repository="https://github.com/example/repo",
        )
    )

    assert registry_service.sync_local() == 1
    assert store.get_registry_skill("gh") is not None


# ---------- API 层：source_missing 契约与降级 ----------


@pytest.fixture()
def roots(tmp_path: Path) -> SimpleNamespace:
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
def env(roots: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLS_SOURCE_ROOT", str(roots.source_root))
    monkeypatch.setenv("GITHUB_SKILL_CACHE_ROOT", str(roots.github_cache))
    monkeypatch.setenv("OPENCLAW_SKILLS_ROOT", str(roots.openclaw))
    monkeypatch.setenv("HERMES_SKILLS_ROOT", str(roots.hermes))
    monkeypatch.setenv("SKILL_MANAGER_STATE_DIR", str(roots.state))
    monkeypatch.setenv("SKILL_MANAGER_TARGETS_MOUNT_ROOT", str(roots.targets))
    monkeypatch.setenv("SKILL_MANAGER_ADMIN_PASSWORD", "test-password")


@pytest.fixture()
def client(env: None):
    from src.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_card_source_missing_flips_with_source_dir(client, env, roots):
    settings = Settings()
    store = SkillStateStore.from_settings(settings)
    store.upsert_registry_skill(
        RegistrySkill(id="ghost", name="Ghost", source="local", path="ghost")
    )

    card = _get_card(client, "ghost")
    assert card["source_missing"] is True

    make_skill(roots.source_root, "ghost", content="---\nname: Ghost\n---")
    card = _get_card(client, "ghost")
    assert card["source_missing"] is False


def test_list_skills_degrades_when_source_root_missing(client, env, roots):
    shutil.rmtree(roots.source_root)

    response = client.get("/api/skills")

    assert response.status_code == 200


def _get_card(client, skill_id: str) -> dict:
    response = client.get("/api/skills")
    assert response.status_code == 200
    return next(card for card in response.json()["items"] if card["id"] == skill_id)

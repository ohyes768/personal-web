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


def test_sync_migrates_unique_move_and_preserves_metadata(registry_service, store, source_root):
    make_skill(source_root, "old/moved")
    original = RegistrySkill(
        id="moved", name="人工名称", source="local", path="old/moved",
        tags=["投研"], summary="人工简介", status="deprecated",
    )
    registry_service.upsert(original)
    (source_root / "new").mkdir()
    (source_root / "old/moved").rename(source_root / "new/moved")

    assert registry_service.sync_local() == 0  # 返回值仍只统计新增
    updated = store.get_registry_skill("moved")
    assert updated == original.model_copy(update={"path": "new/moved"})
    assert registry_service.sync_local() == 0
    assert store.get_registry_skill("moved") == updated


@pytest.mark.parametrize("old_exists", [False, True])
def test_sync_does_not_guess_between_duplicate_ids(registry_service, store, source_root, old_exists):
    make_skill(source_root, "old/duplicate")
    registry_service.sync_local()
    if not old_exists:
        shutil.rmtree(source_root / "old/duplicate")
    make_skill(source_root, "new/duplicate")
    make_skill(source_root, "another/duplicate")

    assert registry_service.sync_local() == 0
    assert store.get_registry_skill("duplicate").path == "old/duplicate"


def test_sync_preserves_valid_old_path(registry_service, store, source_root):
    make_skill(source_root, "old/stays")
    registry_service.sync_local()
    make_skill(source_root, "new/stays")
    assert registry_service.sync_local() == 0
    assert store.get_registry_skill("stays").path == "old/stays"


def test_sync_skips_new_ambiguous_ids(registry_service, store, source_root):
    make_skill(source_root, "first/ambiguous")
    make_skill(source_root, "second/ambiguous")
    assert registry_service.sync_local() == 0
    assert store.get_registry_skill("ambiguous") is None


def test_sync_preserves_github_registration_with_same_local_id(registry_service, store, source_root):
    original = RegistrySkill(id="collision", name="GH", source="github", path=".",
                             repository="https://github.com/example/repo")
    registry_service.upsert(original)
    make_skill(source_root, "collision")
    assert registry_service.sync_local() == 0
    assert store.get_registry_skill("collision") == original


@pytest.mark.requires_symlink
def test_sync_rejects_candidate_with_skill_file_outside_root(registry_service, store, source_root, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("---\nname: Outside\n---", encoding="utf-8")
    store.upsert_registry_skill(RegistrySkill(id="escaped", name="Original", source="local", path="old/escaped"))
    new = source_root / "new/escaped"
    new.mkdir(parents=True)
    (new / "SKILL.md").symlink_to(outside)
    assert registry_service.sync_local() == 0
    assert store.get_registry_skill("escaped").path == "old/escaped"


# ---------- API 层：source_missing 契约与降级 ----------


@pytest.fixture()
def roots(tmp_path: Path) -> SimpleNamespace:
    source_root = tmp_path / "source"
    github_cache = tmp_path / "cache"
    state = tmp_path / "state"
    targets = tmp_path / "targets"
    openclaw = targets / "retired-test-root"
    hermes = targets / "hermes"
    for directory in (source_root, github_cache, state, openclaw, hermes):
        directory.mkdir(parents=True)
    return SimpleNamespace(
        source_root=source_root,
        github_cache=github_cache,
        state=state,
        targets=targets,
        hermes=hermes,
    )


@pytest.fixture()
def env(roots: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLS_SOURCE_ROOT", str(roots.source_root))
    monkeypatch.setenv("GITHUB_SKILL_CACHE_ROOT", str(roots.github_cache))
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


def test_list_migrates_directory_and_clears_source_missing(client, roots):
    make_skill(roots.source_root, "old/moving")
    assert _get_card(client, "moving")["path"] == "old/moving"
    (roots.source_root / "new").mkdir()
    (roots.source_root / "old/moving").rename(roots.source_root / "new/moving")
    card = _get_card(client, "moving")
    assert card["path"] == "new/moving"
    assert card["source_missing"] is False


def _get_card(client, skill_id: str) -> dict:
    response = client.get("/api/skills")
    assert response.status_code == 200
    return next(card for card in response.json()["items"] if card["id"] == skill_id)

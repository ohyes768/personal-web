"""RegistryService（SQLite 登记真源）测试。

覆盖：路径边界、SKILL.md 校验、tags 归一化、github repository+path 唯一、
同 id 替换、删除，以及本地发现与对账（sync_local）。
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.db import SkillStateStore
from src.models import RegistrySkill
from src.services.registry import (
    RegistryService,
    RegistryValidationError,
)


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


def make_local_skill_dir(source_root: Path, dir_name: str) -> None:
    (source_root / dir_name).mkdir(parents=True)
    (source_root / dir_name / "SKILL.md").write_text("---\nname: x\n---", encoding="utf-8")


# ---------- 本地发现 ----------


def test_registry_lists_only_local_directories_with_skill_md(registry_service, source_root):
    make_local_skill_dir(source_root, "ok")
    (source_root / "not-a-skill").mkdir()

    assert [skill.id for skill in registry_service.discover_local()] == ["ok"]


def test_discover_local_skips_hidden_and_excluded_dirs(registry_service, source_root):
    for name in (".hidden", ".cache", "scripts", "__pycache__", "normal"):
        make_local_skill_dir(source_root, name)

    assert [skill.id for skill in registry_service.discover_local()] == ["normal"]


def test_discover_local_uses_nested_relative_path(registry_service, source_root):
    theme = source_root / "theme-a"
    theme.mkdir()
    make_local_skill_dir(theme, "my-skill")

    found = registry_service.discover_local()
    assert [(s.id, s.path) for s in found] == [("my-skill", "theme-a/my-skill")]


# ---------- upsert 校验 ----------


def test_upsert_rejects_local_path_escape(registry_service, store):
    escaped = RegistrySkill(id="escape", name="Escape", source="local", path="../outside")
    with pytest.raises(RegistryValidationError, match="source root"):
        registry_service.upsert(escaped)
    # 校验失败不得写入登记真源
    assert store.count_registry_skills() == 0


def test_upsert_replaces_existing_entry_with_same_id(registry_service, store):
    make_local_skill_dir(registry_service.source_root, "renewable")
    registry_service.upsert(
        RegistrySkill(id="renewable", name="old", source="local", path="renewable")
    )
    registry_service.upsert(
        RegistrySkill(id="renewable", name="new", source="local", path="renewable")
    )

    assert [s.name for s in registry_service.list_skills()] == ["new"]
    assert store.count_registry_skills() == 1


def test_upsert_sorts_and_dedupes_tags(registry_service, source_root):
    make_local_skill_dir(source_root, "tagged")
    registry_service.upsert(
        RegistrySkill(
            id="tagged", name="t", source="local", path="tagged", tags=["b", "a", "b"]
        )
    )

    assert registry_service.list_skills()[0].tags == ["a", "b"]


def test_upsert_rejects_invalid_id(registry_service, source_root):
    with pytest.raises(ValidationError):
        registry_service.upsert(
            RegistrySkill(id="Bad_ID", name="x", source="local", path="x")
        )


def test_upsert_rejects_local_path_without_skill_md(registry_service, source_root):
    (source_root / "bare").mkdir()
    with pytest.raises(RegistryValidationError, match="SKILL.md"):
        registry_service.upsert(
            RegistrySkill(id="bare", name="b", source="local", path="bare")
        )


def test_upsert_rejects_github_path_traversal(registry_service):
    with pytest.raises(RegistryValidationError):
        registry_service.upsert(
            RegistrySkill(
                id="traversal",
                name="t",
                source="github",
                path="../escape",
                repository="https://github.com/a/escape",
            )
        )


# ---------- github repository+path 唯一性 ----------


def test_upsert_rejects_duplicate_github_repository_path(registry_service):
    registry_service.upsert(
        RegistrySkill(
            id="one",
            name="one",
            source="github",
            path=".",
            repository="https://github.com/a/one",
        )
    )
    with pytest.raises(RegistryValidationError, match="duplicate github repository"):
        registry_service.upsert(
            RegistrySkill(
                id="two",
                name="two",
                source="github",
                path=".",
                repository="https://github.com/a/one",
            )
        )


def test_upsert_same_id_does_not_trigger_repo_path_conflict(registry_service):
    """同 id 视为更新，排除自身，不因 repository+path 重复被拒。"""
    skill = RegistrySkill(
        id="one", name="one", source="github", path=".",
        repository="https://github.com/a/one",
    )
    registry_service.upsert(skill)
    registry_service.upsert(skill.model_copy(update={"name": "renamed"}))

    assert [s.name for s in registry_service.list_skills()] == ["renamed"]


def test_upsert_local_entries_never_conflict_on_repo_path(registry_service, source_root):
    make_local_skill_dir(source_root, "one")
    make_local_skill_dir(source_root, "two")
    registry_service.upsert(
        RegistrySkill(id="one", name="one", source="local", path="one")
    )
    registry_service.upsert(
        RegistrySkill(id="two", name="two", source="local", path="two")
    )

    assert [s.id for s in registry_service.list_skills()] == ["one", "two"]


# ---------- remove ----------


def test_remove_deletes_entry(registry_service, source_root):
    make_local_skill_dir(source_root, "alpha")
    make_local_skill_dir(source_root, "beta")
    registry_service.upsert(
        RegistrySkill(id="alpha", name="alpha", source="local", path="alpha")
    )
    registry_service.upsert(
        RegistrySkill(id="beta", name="beta", source="local", path="beta")
    )

    registry_service.remove("alpha")

    assert [s.id for s in registry_service.list_skills()] == ["beta"]


def test_remove_unknown_id_raises(registry_service, source_root):
    make_local_skill_dir(source_root, "alpha")
    registry_service.upsert(
        RegistrySkill(id="alpha", name="alpha", source="local", path="alpha")
    )

    with pytest.raises(RegistryValidationError, match="unknown skill id"):
        registry_service.remove("ghost")
    # 报错时登记真源不变
    assert [s.id for s in registry_service.list_skills()] == ["alpha"]


# ---------- 登记真源持久化 ----------


def test_upsert_persists_created_at_and_updates_updated_at(store, source_root):
    make_local_skill_dir(source_root, "keep")
    service = RegistryService(store, source_root)
    service.upsert(RegistrySkill(id="keep", name="v1", source="local", path="keep"))
    first = _select_timestamps(store, "keep")

    service.upsert(RegistrySkill(id="keep", name="v2", source="local", path="keep"))
    second = _select_timestamps(store, "keep")

    # created_at 保留首次写入值；updated_at 随每次 upsert 刷新
    assert second[0] == first[0]
    assert second[1] >= first[1]
    assert service.get("keep").name == "v2"


def _select_timestamps(store: SkillStateStore, skill_id: str) -> tuple[str, str]:
    with closing(sqlite3.connect(store.db_path)) as conn:
        row = conn.execute(
            "SELECT created_at, updated_at FROM registry_skill WHERE id = ?",
            (skill_id,),
        ).fetchone()
    assert row is not None
    return str(row[0]), str(row[1])


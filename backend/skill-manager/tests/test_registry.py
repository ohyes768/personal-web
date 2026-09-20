"""RegistryService 测试：路径边界、SKILL.md 校验、去重、原子写入与固定 git 参数。

覆盖 implement.md Task 2 给定的两个用例，并补充重复 id、重复 github
repository+path、tags 规范化、agents 保留与原子写入等回归用例。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models import RegistrySkill
from src.services.registry import COMMIT_MESSAGE, REGISTRY_FILENAME, RegistryService, RegistryValidationError


@pytest.fixture()
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    return root


@pytest.fixture()
def registry_service(source_root: Path) -> RegistryService:
    return RegistryService(source_root)


def make_local_skill_dir(source_root: Path, dir_name: str) -> None:
    (source_root / dir_name).mkdir(parents=True)
    (source_root / dir_name / "SKILL.md").write_text("---\nname: x\n---", encoding="utf-8")


def write_registry_file(source_root: Path, payload: dict) -> None:
    (source_root / REGISTRY_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# ---------- 给定用例 ----------


def test_registry_rejects_local_path_escape(registry_service, tmp_path):
    escaped = RegistrySkill(id="escape", name="Escape", source="local", path="../outside")
    with pytest.raises(RegistryValidationError, match="source root"):
        registry_service.upsert(escaped)
    # 校验失败不得把坏条目写入注册表
    assert not (registry_service.registry_path).exists()


def test_registry_lists_only_local_directories_with_skill_md(registry_service, source_root):
    make_local_skill_dir(source_root, "ok")
    (source_root / "not-a-skill").mkdir()

    assert [skill.id for skill in registry_service.discover_local()] == ["ok"]


# ---------- 本地发现 ----------


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


# ---------- 唯一性约束 ----------


def test_load_rejects_duplicate_ids(registry_service, source_root):
    make_local_skill_dir(source_root, "dup")
    entry = {"id": "dup", "name": "dup", "source": "local", "path": "dup"}
    write_registry_file(source_root, {"skills": [entry, entry]})

    with pytest.raises(RegistryValidationError, match="duplicate skill id"):
        registry_service.load()


def test_load_rejects_duplicate_github_repository_path(registry_service, source_root):
    first = {
        "id": "one",
        "name": "one",
        "source": "github",
        "path": ".",
        "repository": "https://github.com/a/one",
    }
    second = {**first, "id": "two", "name": "two"}
    write_registry_file(source_root, {"skills": [first, second]})

    with pytest.raises(RegistryValidationError, match="duplicate github repository"):
        registry_service.load()


def test_upsert_replaces_existing_entry_with_same_id(registry_service, source_root):
    make_local_skill_dir(source_root, "renewable")
    registry_service.upsert(
        RegistrySkill(id="renewable", name="old", source="local", path="renewable")
    )
    registry_service.upsert(
        RegistrySkill(id="renewable", name="new", source="local", path="renewable")
    )

    reloaded = registry_service.load()
    assert [s.name for s in reloaded.skills] == ["new"]


# ---------- 字段规范化与校验 ----------


def test_upsert_sorts_and_dedupes_tags(registry_service, source_root):
    make_local_skill_dir(source_root, "tagged")
    registry_service.upsert(
        RegistrySkill(
            id="tagged", name="t", source="local", path="tagged", tags=["b", "a", "b"]
        )
    )

    assert registry_service.load().skills[0].tags == ["a", "b"]


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


def test_load_rejects_local_skill_without_skill_md(registry_service, source_root):
    entry = {"id": "ghost", "name": "g", "source": "local", "path": "ghost"}
    write_registry_file(source_root, {"skills": [entry]})

    with pytest.raises(RegistryValidationError, match="SKILL.md"):
        registry_service.load()


def test_load_rejects_github_path_traversal(registry_service, source_root):
    entry = {
        "id": "traversal",
        "name": "t",
        "source": "github",
        "path": "../escape",
        "repository": "https://github.com/a/escape",
    }
    write_registry_file(source_root, {"skills": [entry]})

    with pytest.raises(RegistryValidationError):
        registry_service.load()


# ---------- 持久化 ----------


def test_upsert_preserves_agents_and_roundtrips(registry_service, source_root):
    make_local_skill_dir(source_root, "alpha")
    write_registry_file(
        source_root,
        {
            "version": "3.0",
            "updated": "2026-09-20",
            "skills": [{"id": "alpha", "name": "alpha", "source": "local", "path": "alpha"}],
            "agents": {"openclaw": {"description": "研究", "skills": ["alpha"]}},
        },
    )
    make_local_skill_dir(source_root, "beta")
    registry_service.upsert(
        RegistrySkill(id="beta", name="beta", source="local", path="beta")
    )

    reloaded = registry_service.load()
    assert sorted(s.id for s in reloaded.skills) == ["alpha", "beta"]
    assert reloaded.agents["openclaw"].description == "研究"
    assert reloaded.agents["openclaw"].skills == ["alpha"]


def test_upsert_atomic_write_leaves_no_temp_files(registry_service, source_root):
    make_local_skill_dir(source_root, "clean")
    registry_service.upsert(
        RegistrySkill(id="clean", name="c", source="local", path="clean")
    )

    assert {p.name for p in source_root.iterdir()} == {"clean", REGISTRY_FILENAME}
    # 输出必须是合法 JSON 且包含已登记条目
    raw = json.loads(registry_service.registry_path.read_text(encoding="utf-8"))
    assert raw["skills"][0]["id"] == "clean"


def test_load_missing_registry_raises(registry_service):
    with pytest.raises(RegistryValidationError, match="not found"):
        registry_service.load()


# ---------- 固定 git 提交 ----------


def test_commit_registry_change_runs_fixed_git_arguments(
    registry_service, source_root, monkeypatch
):
    calls: list[tuple[list[str], dict]] = []

    def fake_run(cmd, **kwargs):
        calls.append((list(cmd), kwargs))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("src.services.registry.subprocess.run", fake_run)

    registry_service.commit_registry_change()

    assert [argv for argv, _ in calls] == [
        ["git", "add", REGISTRY_FILENAME],
        ["git", "commit", "-m", COMMIT_MESSAGE],
    ]
    assert all(kwargs.get("shell") is False for _, kwargs in calls)
    assert all(Path(kwargs["cwd"]) == registry_service.source_root for _, kwargs in calls)

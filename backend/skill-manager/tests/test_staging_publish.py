"""仓库缓存直链、旧缓存布局迁移与 active 旧链接自动迁移测试。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.db import (
    DeploymentRecord,
    HistoryEntry,
    SkillStateStore,
)
from src.models import RegistrySkill, SkillSource, TargetKey
from src.services.git_cache import GitCacheService
from src.services.migration import (
    migrate_legacy_cache,
    republish_active_github_skills,
)
from src.services.publisher import (
    InvalidSourceError,
    Publisher,
)
from src.services.registry import RegistryService

CANONICAL_URL = "https://github.com/example/two-skills"


def run_git(*argv: str, cwd: Path) -> str:
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
def settings(roots):
    return Settings(
        skills_source_root=roots.source_root,
        github_skill_cache_root=roots.github_cache,
        hermes_skills_root=roots.hermes,
        state_dir=roots.state,
        admin_password="test-password",
        targets_mount_root=roots.targets,
    )


@pytest.fixture()
def store(settings):
    return SkillStateStore(settings.state_dir / "skill-manager.sqlite3")


@pytest.fixture()
def publisher(settings, store):
    return Publisher(settings, store)


@pytest.fixture()
def git_cache(settings, store):
    return GitCacheService(settings, store)


@pytest.fixture()
def registry(store, roots):
    return RegistryService(store, roots.source_root)


@pytest.fixture()
def shared_repo_cache(roots) -> Path:
    """模拟共享缓存中已检出的合集仓库：skills/alpha 本体 + 根级 tools/。"""
    repo_dir = roots.github_cache / "repos" / "example__two-skills"
    skill_dir = repo_dir / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: alpha\n---\nuses tools/lib.py\n", encoding="utf-8"
    )
    (skill_dir / "run.md").write_text("run\n", encoding="utf-8")
    tools = repo_dir / "tools"
    tools.mkdir()
    (tools / "lib.py").write_text("LIB\n", encoding="utf-8")
    (repo_dir / "README.md").write_text("repo\n", encoding="utf-8")
    (repo_dir / ".git").mkdir()  # 假 .git：验证绝不进入产物
    (repo_dir / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    return repo_dir


@pytest.fixture()
def github_skill() -> RegistrySkill:
    return RegistrySkill(
        id="two-skills-alpha",
        name="Alpha",
        source=SkillSource.GITHUB,
        path="skills/alpha",
        repository=CANONICAL_URL,
        shared_paths=["tools"],
    )


# ---------- 下架只删除链接，保留仓库缓存 ----------


@pytest.mark.requires_symlink
def test_unpublish_removes_link_but_keeps_repository(
    publisher, shared_repo_cache, github_skill, store, roots, settings
):
    from src.services.publisher import resolve_github_source

    source = resolve_github_source(settings, github_skill, shared_repo_cache)
    publisher.publish(github_skill.id, TargetKey.HERMES, source, "c" * 40)
    publisher.unpublish(github_skill.id, TargetKey.HERMES)
    assert not (roots.hermes / github_skill.id).is_symlink()
    assert source.is_dir()
    assert (shared_repo_cache / "tools" / "lib.py").is_file()
    assert not (roots.github_cache / "staging").exists()
    record = store.get_deployment(github_skill.id, "hermes")
    assert record is not None and record.status == "removed"


# ---------- 存量迁移（design §5.3） ----------


def _seed_legacy_cache(roots, skill_id: str) -> Path:
    legacy = roots.github_cache / skill_id
    (legacy / ".git").mkdir(parents=True)
    (legacy / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    return legacy


def test_migrate_legacy_cache_moves_single_copy(roots, settings, registry):
    skill = RegistrySkill(
        id="two-skills",
        name="t",
        source=SkillSource.GITHUB,
        path="skills/alpha",
        repository=CANONICAL_URL,
    )
    registry.upsert(skill)
    _seed_legacy_cache(roots, "two-skills")

    moved, discarded = migrate_legacy_cache(settings, registry.list_skills())

    assert (moved, discarded) == (1, 0)
    assert not (roots.github_cache / "two-skills").exists()
    assert (roots.github_cache / "repos" / "example__two-skills" / ".git").is_dir()


def test_migrate_legacy_cache_discards_extra_copies(roots, settings, registry):
    """同仓库多条目各自的旧整仓缓存：保留其一，其余删除。"""
    for skill_id, path in (
        ("two-skills", "skills/alpha"),
        ("two-skills-beta", "skills/beta"),
    ):
        registry.upsert(
            RegistrySkill(
                id=skill_id,
                name=skill_id,
                source=SkillSource.GITHUB,
                path=path,
                repository=CANONICAL_URL,
            )
        )
        _seed_legacy_cache(roots, skill_id)

    moved, discarded = migrate_legacy_cache(settings, registry.list_skills())

    assert (moved, discarded) == (1, 1)
    # 旧 skill.id 目录全部消失，只剩仓库维度目录
    assert list(
        p.name for p in roots.github_cache.iterdir() if p.is_dir()
    ) == ["repos"]
    assert (roots.github_cache / "repos" / "example__two-skills" / ".git").is_dir()


def test_migrate_legacy_cache_noop_when_both_missing(roots, settings, registry):
    registry.upsert(
        RegistrySkill(
            id="two-skills",
            name="t",
            source=SkillSource.GITHUB,
            path="skills/alpha",
            repository=CANONICAL_URL,
        )
    )

    moved, discarded = migrate_legacy_cache(settings, registry.list_skills())

    assert (moved, discarded) == (0, 0)


def test_migrate_legacy_cache_keeps_existing_repo_dir(roots, settings, registry):
    """目标 repos 目录已存在（新代码先跑过）：legacy 副本按多余删除。"""
    registry.upsert(
        RegistrySkill(
            id="two-skills",
            name="t",
            source=SkillSource.GITHUB,
            path="skills/alpha",
            repository=CANONICAL_URL,
        )
    )
    _seed_legacy_cache(roots, "two-skills")
    existing = roots.github_cache / "repos" / "example__two-skills"
    (existing / ".git").mkdir(parents=True)

    moved, discarded = migrate_legacy_cache(settings, registry.list_skills())

    assert (moved, discarded) == (0, 1)
    assert not (roots.github_cache / "two-skills").exists()


# ---------- active 部署自动重发布（design §5.3） ----------


def _init_real_git_repo(path: Path) -> str:
    """初始化真实 git 仓库（含一次 commit），返回 HEAD revision。"""
    path.mkdir(parents=True)
    run_git("init", cwd=path)
    run_git("config", "user.email", "fixture@example.com", cwd=path)
    run_git("config", "user.name", "Fixture", cwd=path)
    (path / "SKILL.md").write_text("---\nname: r\n---\n", encoding="utf-8")
    run_git("add", "-A", cwd=path)
    run_git("commit", "-m", "fixture", cwd=path)
    return run_git("rev-parse", "HEAD", cwd=path).strip()


@pytest.mark.requires_symlink
def test_republish_active_github_skills_rebuilds_link_to_repository(
    roots, settings, store, publisher, git_cache, registry
):
    """旧快照链接启动时直接迁移到仓库根目录，不创建新快照。"""
    revision = _init_real_git_repo(roots.github_cache / "repos" / "example__example-rep")
    skill = RegistrySkill(
        id="example-rep",
        name="rep",
        source=SkillSource.GITHUB,
        path=".",
        repository="https://github.com/example/example-rep",
    )
    registry.upsert(skill)
    # 迁移前的旧链接（指向已不存在的旧布局路径）+ active 记录
    stale_target = roots.github_cache / "staging" / skill.id / revision[:12]
    stale_target.mkdir(parents=True)
    (stale_target / "SKILL.md").write_text("old snapshot", encoding="utf-8")
    link = roots.hermes / skill.id
    link.symlink_to(stale_target, target_is_directory=True)
    store.upsert_deployment(
        DeploymentRecord(
            skill_id=skill.id,
            target="hermes",
            source_revision=revision,
            source_path=str(stale_target),
            current_link_target=str(stale_target),
            status="active",
            published_at="2026-09-30T00:00:00+00:00",
        )
    )

    republished = republish_active_github_skills(
        settings, registry, store, publisher, git_cache
    )

    assert republished == 1
    # 链接被替换到缓存仓库根目录，内容可用；旧快照保留，不做破坏性清理
    assert link.is_symlink()
    resolved = link.resolve()
    assert resolved == (
        roots.github_cache / "repos" / "example__example-rep"
    ).resolve()
    assert (resolved / "SKILL.md").is_file()
    record = store.get_deployment(skill.id, "hermes")
    assert record is not None and record.status == "active"
    assert record.current_link_target == str(resolved)
    assert (stale_target / "SKILL.md").read_text() == "old snapshot"
    assert republish_active_github_skills(settings, registry, store, publisher, git_cache) == 0


def test_republish_records_history_error_when_cache_missing(
    roots, settings, store, publisher, git_cache, registry
):
    """缓存缺失：记 deployment_history error（action=publish），不抛出。"""
    skill = RegistrySkill(
        id="example-gone",
        name="gone",
        source=SkillSource.GITHUB,
        path=".",
        repository="https://github.com/example/example-gone",
    )
    registry.upsert(skill)
    store.upsert_deployment(
        DeploymentRecord(
            skill_id=skill.id,
            target="hermes",
            source_revision="",
            source_path="",
            current_link_target="",
            status="active",
            published_at="2026-09-30T00:00:00+00:00",
        )
    )

    republished = republish_active_github_skills(
        settings, registry, store, publisher, git_cache
    )

    assert republished == 0
    history = store.list_history(skill_id=skill.id, target="hermes")
    failures = [e for e in history if e.result == "error"]
    assert failures and failures[0].action == "publish"
    assert isinstance(failures[0], HistoryEntry)
    assert "does not exist" in (failures[0].error or "")

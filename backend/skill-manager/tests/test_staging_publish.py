"""staging 发布与存量迁移测试（2026-09-30 批量登记任务 design §4/§5.3/§8）。

- Publisher.stage_github_skill：快照组装（本体 + shared_paths 随行资源、
  .git 排除）、资源缺失 blocked、同 rev 复用、过期 rev 清理保留 2 份；
- unpublish 只删链接不动 staging；
- migration.migrate_legacy_cache 三分支（移动/多余副本删除/双缺失）与
  republish_active_github_skills（无网络重发布、缓存缺失记 history error）。
"""

from __future__ import annotations

import os
import subprocess
import time
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
    PublishBlockedError,
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
def settings(roots):
    return Settings(
        skills_source_root=roots.source_root,
        github_skill_cache_root=roots.github_cache,
        openclaw_skills_root=roots.openclaw,
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


# ---------- staging 组装 ----------


def test_stage_copies_skill_body_and_shared_paths(
    publisher, shared_repo_cache, github_skill, roots
):
    staged = publisher.stage_github_skill(github_skill, "a" * 40, shared_repo_cache)

    assert staged == roots.github_cache / "staging" / "two-skills-alpha" / ("a" * 12)
    # 本体（含 SKILL.md）与 shared_paths 随行资源都进快照
    assert (staged / "SKILL.md").is_file()
    assert (staged / "run.md").is_file()
    assert (staged / "tools" / "lib.py").read_text(encoding="utf-8") == "LIB\n"
    # 仓库内但未被引用的内容与 .git 绝不进入产物
    assert not (staged / "README.md").exists()
    assert not (staged / ".git").exists()
    assert not (staged / "skills").exists()


def test_stage_rejects_missing_shared_path(publisher, shared_repo_cache, github_skill):
    broken = github_skill.model_copy(update={"shared_paths": ["gone"]})
    with pytest.raises(PublishBlockedError, match="gone"):
        publisher.stage_github_skill(broken, "a" * 40, shared_repo_cache)


def test_stage_rejects_repo_dir_outside_cache_root(
    publisher, tmp_path, github_skill
):
    outside = tmp_path / "outside-repo"
    skill_dir = outside / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("x", encoding="utf-8")
    with pytest.raises(InvalidSourceError, match="outside the GitHub cache root"):
        publisher.stage_github_skill(github_skill, "a" * 40, outside)


def test_stage_reuses_existing_rev_dir_and_drops_tmp(
    publisher, shared_repo_cache, github_skill
):
    first = publisher.stage_github_skill(github_skill, "b" * 40, shared_repo_cache)
    sentinel = first / "SKILL.md"
    before = sentinel.read_text(encoding="utf-8")

    second = publisher.stage_github_skill(github_skill, "b" * 40, shared_repo_cache)

    assert second == first
    # 复用不重组：既有内容原样保留（未被重写）
    assert sentinel.read_text(encoding="utf-8") == before
    # 不留组装临时目录
    assert not any(
        p.name.startswith(".") and p.name.endswith(".next")
        for p in publisher.staging_root().iterdir()
    )


def test_stage_keeps_only_two_latest_revs(
    publisher, shared_repo_cache, github_skill
):
    # 显式设置各 rev 目录 mtime 模拟不同发布时刻：规避平台时钟粒度
    # （Windows ~15.6ms）导致同刻目录排序不确定。给已建 rev 设递增的
    # 过去时间，最新 stage 的真实 mtime 自然最大。
    base = time.time()
    for i, revision in enumerate(("1" * 40, "2" * 40, "3" * 40)):
        publisher.stage_github_skill(github_skill, revision, shared_repo_cache)
        os.utime(
            publisher.staging_root() / "two-skills-alpha" / revision[:12],
            (base - 30 + i * 10, base - 30 + i * 10),
        )

    rev_dirs = sorted(
        p.name for p in (publisher.staging_root() / "two-skills-alpha").iterdir()
    )
    assert rev_dirs == ["2" * 12, "3" * 12]


def test_planned_staging_dir_is_read_only_computation(publisher):
    planned = publisher.planned_staging_dir("some-skill", "abcdef1234567890")
    assert planned.name == "abcdef123456"
    assert not planned.exists()  # 只读计算，不创建目录
    assert publisher.planned_staging_dir("some-skill", "") .name == "uncached"


def test_resolve_registry_source_rejects_github_entries(settings, github_skill):
    """github 条目的发布源是 staging（stage_github_skill），直链解析即拒。"""
    from src.services.publisher import resolve_registry_source

    with pytest.raises(InvalidSourceError, match="staging"):
        resolve_registry_source(settings, github_skill)


# ---------- unpublish 不动 staging ----------


@pytest.mark.requires_symlink
def test_unpublish_removes_link_but_keeps_staging(
    publisher, shared_repo_cache, github_skill, store, roots
):
    staged = publisher.stage_github_skill(github_skill, "c" * 40, shared_repo_cache)
    publisher.publish(
        github_skill.id, TargetKey.OPENCLAW, staged, "c" * 40
    )

    publisher.unpublish(github_skill.id, TargetKey.OPENCLAW)

    assert not (roots.openclaw / github_skill.id).is_symlink()
    # staging 快照与 deployment removed 记录保留
    assert staged.is_dir()
    record = store.get_deployment(github_skill.id, "openclaw")
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
def test_republish_active_github_skills_rebuilds_link_via_staging(
    roots, settings, store, publisher, git_cache, registry
):
    """迁移后旧 symlink target 失效：启动重发布组装 staging 并替换链接。"""
    revision = _init_real_git_repo(roots.github_cache / "repos" / "example__rep")
    skill = RegistrySkill(
        id="example-rep",
        name="rep",
        source=SkillSource.GITHUB,
        path=".",
        repository="https://github.com/example/example-rep",
    )
    registry.upsert(skill)
    # 迁移前的旧链接（指向已不存在的旧布局路径）+ active 记录
    stale_target = roots.github_cache / "example-rep"
    link = roots.openclaw / skill.id
    link.symlink_to(stale_target, target_is_directory=True)
    store.upsert_deployment(
        DeploymentRecord(
            skill_id=skill.id,
            target="openclaw",
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
    # 链接被替换到 staging rev 目录，内容可用
    assert link.is_symlink()
    resolved = link.resolve()
    assert resolved == (
        roots.github_cache / "staging" / skill.id / revision[:12]
    ).resolve()
    assert (resolved / "SKILL.md").is_file()
    record = store.get_deployment(skill.id, "openclaw")
    assert record is not None and record.status == "active"
    assert record.current_link_target == str(resolved)


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

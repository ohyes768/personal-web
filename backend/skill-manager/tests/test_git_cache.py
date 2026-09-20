"""GitCacheService 测试：URL 规范化、SKILL.md 候选扫描、工作区清理、
只读更新检查与缓存 checkout（design 5 / Task 4）。

fixture 用本地 bare 仓库充当 GitHub 远端：通过 service 的 `remotes`
映射参数把规范化 github.com URL 指到该仓库，Git 语义与线上一致且完全离线。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.db import SkillStateStore
from src.models import RegistrySkill
from src.services.git_cache import (
    CacheValidationError,
    GitCacheError,
    GitCacheService,
    GitOperationError,
    InvalidRepositoryError,
)

CANONICAL_URL = "https://github.com/example/two-skills"
BROKEN_URL = "https://github.com/example/broken"
UNRELATED_URL = "https://github.com/example/unrelated"


def run_git(*argv: str, cwd: Path | None = None) -> str:
    """测试内固定参数 git 调用，返回 stdout。"""
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
def upstream_repo(tmp_path):
    """构造"远端"：工作仓库（两个 skill + 应被忽略的杂项）→ bare clone。

    返回 (bare 路径, HEAD revision)。
    """
    work = tmp_path / "upstream-work"
    work.mkdir()
    run_git("init", str(work))
    run_git("config", "user.email", "fixture@example.com", cwd=work)
    run_git("config", "user.name", "Fixture", cwd=work)
    for rel in ("skills/alpha", "skills/beta"):
        (work / rel).mkdir(parents=True)
        (work / rel / "SKILL.md").write_text(
            f"---\nname: {rel}\n---\n", encoding="utf-8"
        )
    # 必须被扫描忽略的内容：隐藏目录与工具目录中的 SKILL.md
    hidden = work / ".github" / "bots"
    hidden.mkdir(parents=True)
    (hidden / "SKILL.md").write_text("hidden", encoding="utf-8")
    tool_dir = work / "skills" / "alpha" / "node_modules"
    tool_dir.mkdir()
    (tool_dir / "SKILL.md").write_text("tool", encoding="utf-8")
    run_git("add", "-A", cwd=work)
    run_git("commit", "-m", "fixture: two skills", cwd=work)
    run_git("tag", "v1.0", cwd=work)

    bare = tmp_path / "upstream.git"
    run_git("clone", "--bare", str(work), str(bare))
    revision = run_git("rev-parse", "HEAD", cwd=bare).strip()
    return SimpleNamespace(bare=bare, revision=revision)


@pytest.fixture()
def git_cache(settings, store, upstream_repo, tmp_path):
    """remotes 映射：规范化 URL → 本地 bare 仓库（离线）；broken URL 映射到
    不存在的本地路径，用于离线验证 clone 失败路径。"""
    return GitCacheService(
        settings,
        store,
        remotes={
            CANONICAL_URL: str(upstream_repo.bare),
            BROKEN_URL: str(tmp_path / "missing.git"),
        },
    )


@pytest.fixture()
def registered_github_skill():
    return RegistrySkill(
        id="two-skills",
        name="Two Skills",
        source="github",
        path="skills/alpha",
        repository=CANONICAL_URL,
    )


# ---------- 给定用例（implement.md Task 4） ----------


def test_scan_returns_each_skill_md_directory(git_cache):
    candidates = git_cache.scan(CANONICAL_URL)

    # .github/bots 与 node_modules 内的 SKILL.md 被忽略
    assert [candidate.path for candidate in candidates] == [
        "skills/alpha",
        "skills/beta",
    ]


def test_scan_rejects_non_github_and_file_urls(git_cache):
    for url in (
        "file:///tmp/skill",
        "ssh://git@github.com/a/b",
        "https://gitlab.com/a/b",
    ):
        with pytest.raises(InvalidRepositoryError):
            git_cache.scan(url)


def test_check_updates_does_not_change_cache(
    git_cache, registered_github_skill, roots
):
    before = git_cache.current_revision(registered_github_skill.id)

    update = git_cache.check_update(registered_github_skill)

    assert git_cache.current_revision(registered_github_skill.id) == before
    assert update.remote_revision
    # 检查更新绝不下载：缓存根目录始终为空
    assert not any(roots.github_cache.iterdir())


# ---------- URL 规范化 ----------


def test_normalize_repository_strips_git_suffix(git_cache):
    assert (
        git_cache.normalize_repository("https://github.com/example/two-skills.git")
        == CANONICAL_URL
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/skill",
        "ssh://git@github.com/a/b",
        "git@github.com:a/b.git",
        "http://github.com/a/b",
        "https://gitlab.com/a/b",
        "https://github.com/a/b/tree/main",
        "https://github.com/../etc",
        "https://github.com/owner",
        "not a url",
    ],
)
def test_normalize_repository_rejects_non_canonical_urls(git_cache, url):
    with pytest.raises(InvalidRepositoryError):
        git_cache.normalize_repository(url)


# ---------- 扫描工作区清理 ----------


def test_scan_workspace_is_cleaned_after_success(git_cache, roots):
    git_cache.scan(CANONICAL_URL)

    scan_parent = roots.state / "scan"
    assert scan_parent.is_dir()
    assert not any(scan_parent.iterdir())


def test_scan_workspace_is_cleaned_after_clone_failure(git_cache, roots):
    # BROKEN_URL 映射到不存在的本地仓库：clone 失败且完全离线
    with pytest.raises(GitCacheError):
        git_cache.scan(BROKEN_URL)

    scan_parent = roots.state / "scan"
    assert not any(scan_parent.iterdir())


# ---------- 更新检查 ----------


def test_check_update_persists_github_check_record(
    git_cache, registered_github_skill, store, upstream_repo
):
    update = git_cache.check_update(registered_github_skill)

    record = store.get_github_check(registered_github_skill.id)
    assert record is not None
    assert record.remote_revision == update.remote_revision == upstream_repo.revision
    assert record.remote_tags == "v1.0"
    assert record.result == "ok"


def test_check_update_flags_update_when_cache_is_missing(
    git_cache, registered_github_skill
):
    update = git_cache.check_update(registered_github_skill)

    assert update.cached_revision == ""
    assert update.has_update is True
    assert update.remote_tags == ["v1.0"]


def test_check_update_reports_no_update_when_cache_is_current(
    git_cache, registered_github_skill, upstream_repo
):
    git_cache.ensure_cached(registered_github_skill, upstream_repo.revision)

    update = git_cache.check_update(registered_github_skill)

    assert update.cached_revision == upstream_repo.revision
    assert update.has_update is False


def test_check_update_rejects_local_skill(git_cache):
    local = RegistrySkill(id="local-one", name="L", source="local", path=".")

    with pytest.raises(InvalidRepositoryError):
        git_cache.check_update(local)


def test_check_update_rejects_non_github_url(git_cache, registered_github_skill):
    moved = registered_github_skill.model_copy(
        update={"repository": "https://gitlab.com/a/b"}
    )

    with pytest.raises(InvalidRepositoryError):
        git_cache.check_update(moved)


def test_check_update_failure_is_isolated_and_recorded(
    settings, store, upstream_repo, tmp_path
):
    # 未映射到有效远端的 URL 映射到不存在的本地路径，确保离线失败
    offline = GitCacheService(
        settings,
        store,
        remotes={UNRELATED_URL: str(tmp_path / "missing-remote.git")},
    )
    skill = RegistrySkill(
        id="two-skills",
        name="Two Skills",
        source="github",
        path="skills/alpha",
        repository=UNRELATED_URL,
    )

    with pytest.raises(GitOperationError):
        offline.check_update(skill)

    record = store.get_github_check(skill.id)
    assert record is not None
    assert record.result == "error"
    assert record.error


# ---------- 缓存 checkout ----------


def test_ensure_cached_clones_and_checks_out_requested_revision(
    git_cache, registered_github_skill, roots, upstream_repo
):
    skill_dir = git_cache.ensure_cached(
        registered_github_skill, upstream_repo.revision
    )

    assert (skill_dir / "SKILL.md").is_file()
    expected = (
        roots.github_cache / "two-skills" / "skills" / "alpha"
    ).resolve()
    assert skill_dir == expected
    assert git_cache.current_revision("two-skills") == upstream_repo.revision


def test_cache_checkout_rejects_missing_registered_subdirectory(
    git_cache, registered_github_skill, upstream_repo
):
    git_cache.ensure_cached(registered_github_skill, upstream_repo.revision)

    moved = registered_github_skill.model_copy(update={"path": "gone"})
    with pytest.raises(CacheValidationError, match="SKILL.md"):
        git_cache.ensure_cached(moved, upstream_repo.revision)


def test_ensure_cached_rejects_traversal_path(
    git_cache, registered_github_skill, roots, upstream_repo
):
    moved = registered_github_skill.model_copy(update={"path": "../escape"})

    with pytest.raises(CacheValidationError):
        git_cache.ensure_cached(moved, upstream_repo.revision)
    # 非法路径在发起任何 git 操作前被拒绝，缓存根保持为空
    assert not any(roots.github_cache.iterdir())


def test_current_revision_is_empty_without_cache(git_cache):
    assert git_cache.current_revision("never-cached") == ""

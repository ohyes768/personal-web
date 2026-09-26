"""GitCacheService 测试：URL 规范化、SKILL.md 候选扫描、工作区清理、
只读更新检查与缓存 checkout（design 5 / Task 4）。

fixture 用本地 bare 仓库充当 GitHub 远端：通过 service 的 `remotes`
映射参数把规范化 github.com URL 指到该仓库，Git 语义与线上一致且完全离线。
"""

from __future__ import annotations

import io
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
    GitProgress,
    GitTimeoutError,
    InvalidRepositoryError,
    _ProgressLineSplitter,
    cleanup_stale_workspaces,
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
    """remotes 映射：规范化 URL → 本地 bare 仓库的 file:// 地址（离线，且
    强制走传输协议以产生真实 `--progress` 进度流）；broken URL 映射到
    不存在的本地路径，用于离线验证 clone 失败路径。"""
    return GitCacheService(
        settings,
        store,
        remotes={
            CANONICAL_URL: f"file:///{upstream_repo.bare.as_posix()}",
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
        "https://github.com/owner/..",
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


# ---------- 流式 git 执行器（09-26 后台任务化 Task 1） ----------

# 真实 `git clone --progress --depth 1 file://…` stderr 抓样（裁剪重复帧）：
# 保留 \r 覆盖刷新、remote: 协商行、receiving 帧之间穿插 negotiating 行、
# 行尾填充空格与 done 行等真实形态
SAMPLE_CLONE_PROGRESS = (
    "Cloning into 'dst'...\n"
    "remote: Enumerating objects: 19, done.        \n"
    "remote: Counting objects:   5% (1/19)        \r"
    "remote: Counting objects:  52% (10/19)        \r"
    "remote: Counting objects: 100% (19/19), done.        \n"
    "remote: Compressing objects:  33% (3/9)        \r"
    "remote: Compressing objects: 100% (9/9), done.        \n"
    "Receiving objects:   5% (1/19)\r"
    "Receiving objects:  15% (3/19)\r"
    "remote: Total 19 (delta 0), reused 0 (delta 0), pack-reused 0 (from 0)        \n"
    "Receiving objects:  42% (8/19)\r"
    "Receiving objects: 100% (19/19)\r"
    "Receiving objects: 100% (19/19), 22.27 KiB | 1.39 MiB/s, done.\n"
    "Resolving deltas:   0% (0/9)\r"
    "Resolving deltas:  55% (5/9)\r"
    "Resolving deltas: 100% (9/9), done.\n"
)


class _FrameRecorder:
    """收集进度帧的回调桩。"""

    def __init__(self) -> None:
        self.frames: list[GitProgress] = []

    def __call__(self, frame: GitProgress) -> None:
        self.frames.append(frame)


def _feed_in_chunks(text: str, size: int = 37) -> list[GitProgress]:
    """把完整流按固定块大小喂给 splitter，覆盖行被块边界切断的场景。"""
    splitter = _ProgressLineSplitter()
    frames: list[GitProgress] = []
    for start in range(0, len(text), size):
        frames.extend(splitter.feed(text[start : start + size]))
    frames.extend(splitter.flush())
    return frames


class _FakeHangingGitPopen:
    """假 git 进程（design/implement Task 1 超时测试）：ls-remote 秒回固定
    HEAD；其余命令（clone）输出一帧 receiving 进度后挂死不退出。"""

    def __init__(self, cmd: list[str], **kwargs: object) -> None:
        self.cmd = cmd
        self.killed = False
        if "ls-remote" in cmd:
            self.stdout = io.StringIO("1f2e3d4c5b6a\tHEAD\n")
            self.stderr = io.StringIO("")
            self._hang = False
        else:
            self.stdout = io.StringIO("")
            self.stderr = io.StringIO(
                "Receiving objects:  45% (1589/3531) | 51.00 KiB/s\r"
            )
            self._hang = True

    def wait(self, timeout: float | None = None) -> int:
        if self._hang:
            raise subprocess.TimeoutExpired(self.cmd, timeout)
        return 0

    def kill(self) -> None:
        self.killed = True


def test_progress_splitter_classifies_real_clone_stream():
    frames = _feed_in_chunks(SAMPLE_CLONE_PROGRESS)

    assert frames, "真实进度流必须解析出帧"
    assert {frame.phase for frame in frames} == {
        "negotiating",
        "receiving",
        "resolving",
    }
    # negotiating 来自 remote: 行（远端枚举/计数/压缩）：无客户端侧百分比
    assert all(
        frame.percent is None
        for frame in frames
        if frame.phase == "negotiating"
    )
    assert [
        frame.percent for frame in frames if frame.phase == "receiving"
    ] == [5, 15, 42, 100, 100]
    assert [
        frame.percent for frame in frames if frame.phase == "resolving"
    ] == [0, 55, 100]
    final_receiving = [
        frame for frame in frames if frame.phase == "receiving"
    ][-1]
    assert "1.39 MiB/s" in final_receiving.detail


def test_progress_splitter_keeps_partial_line_until_flush():
    splitter = _ProgressLineSplitter()

    # 残尾（无 \r/\n 结尾）必须留在缓冲，等待后续块拼出完整行
    assert splitter.feed("Receiving objects:  45% (1589/3531) | 51.0") == []
    assert splitter.feed("0 KiB/s") == []

    frames = splitter.flush()
    assert [frame.percent for frame in frames] == [45]
    assert frames[0].phase == "receiving"
    assert "51.00 KiB/s" in frames[0].detail


def test_progress_splitter_ignores_non_progress_lines():
    splitter = _ProgressLineSplitter()

    frames = splitter.feed("Cloning into 'dst'...\nwarning: lf will be\n\r\n")

    assert frames == []


def test_run_git_streaming_returns_stdout_and_emits_progress(
    git_cache, upstream_repo, tmp_path
):
    destination = tmp_path / "stream-dst"
    recorder = _FrameRecorder()

    stdout = git_cache._run_git_streaming(
        [
            "clone",
            "--depth",
            "1",
            "--progress",
            f"file:///{upstream_repo.bare.as_posix()}",
            str(destination),
        ],
        recorder,
    )

    assert stdout == ""  # clone 不产生 stdout 输出
    assert (destination / ".git").is_dir()
    assert any(frame.phase == "receiving" for frame in recorder.frames)
    assert all(
        frame.phase in {"negotiating", "receiving", "resolving"}
        for frame in recorder.frames
    )


def test_run_git_streaming_timeout_kills_process_and_raises(
    git_cache, tmp_path, monkeypatch
):
    created: list[_FakeHangingGitPopen] = []

    class RecordingFakePopen(_FakeHangingGitPopen):
        def __init__(self, cmd, **kwargs):
            super().__init__(cmd, **kwargs)
            created.append(self)

    monkeypatch.setattr(subprocess, "Popen", RecordingFakePopen)
    recorder = _FrameRecorder()

    with pytest.raises(GitTimeoutError, match="timed out"):
        git_cache._run_git_streaming(
            ["clone", str(tmp_path / "irrelevant.git"), str(tmp_path / "dst")],
            recorder,
            timeout=0.2,
        )

    # kill 前进度帧已被读线程解析上报；假进程确实被 kill
    assert [frame.percent for frame in recorder.frames] == [45]
    assert created and created[0].killed is True


def test_run_git_streaming_nonzero_exit_wraps_full_stderr(git_cache, tmp_path):
    recorder = _FrameRecorder()

    with pytest.raises(GitOperationError) as excinfo:
        git_cache._run_git_streaming(
            ["clone", str(tmp_path / "missing.git"), str(tmp_path / "dst")],
            recorder,
        )

    # 与 _run_git 失败语义一致：message 以 "git <子命令> failed:" 起始并
    # 拼接完整 stderr
    assert str(excinfo.value).startswith("git clone failed:")
    assert recorder.frames == []


def test_scan_forwards_progress_callback(git_cache):
    recorder = _FrameRecorder()

    candidates = git_cache.scan(CANONICAL_URL, on_progress=recorder)

    assert [candidate.path for candidate in candidates] == [
        "skills/alpha",
        "skills/beta",
    ]
    assert any(frame.phase == "receiving" for frame in recorder.frames)


def test_ensure_cached_forwards_progress_callback(
    git_cache, registered_github_skill, upstream_repo
):
    recorder = _FrameRecorder()

    skill_dir = git_cache.ensure_cached(
        registered_github_skill, upstream_repo.revision, on_progress=recorder
    )

    assert (skill_dir / "SKILL.md").is_file()
    assert any(frame.phase == "receiving" for frame in recorder.frames)


# ---------- 半成品缓存根治（09-26 后台任务化 Task 4 / design §3-§4） ----------


class _FakeFailingGitPopen:
    """假 git 进程：clone 输出一帧 receiving 进度后以非零码退出，
    模拟下载中途失败（其余命令不会走到）。"""

    def __init__(self, cmd: list[str], **kwargs: object) -> None:
        self.cmd = cmd
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("Receiving objects:  45% (1589/3531)\r")

    def wait(self, timeout: float | None = None) -> int:
        return 128

    def kill(self) -> None:
        return None


def test_ensure_cached_clone_failure_leaves_no_tmp_or_partial_cache(
    git_cache, registered_github_skill, roots, monkeypatch
):
    """clone 中途失败：本次 .tmp 临时目录被清理，正式缓存目录不存在（AC6）；
    进度帧确实经流式执行器上报，证明 clone 走的是 .tmp 流式路径。"""
    frames: list[GitProgress] = []
    monkeypatch.setattr(subprocess, "Popen", _FakeFailingGitPopen)

    with pytest.raises(GitOperationError):
        git_cache.ensure_cached(
            registered_github_skill, "0f2e3d4", on_progress=frames.append
        )

    assert [frame.percent for frame in frames] == [45]
    tmp_parent = roots.github_cache / ".tmp"
    assert tmp_parent.is_dir()
    assert not any(tmp_parent.iterdir())
    assert not (roots.github_cache / "two-skills").exists()


def test_ensure_cached_first_clone_lands_via_tmp_rename(
    git_cache, registered_github_skill, roots, upstream_repo
):
    """首次 clone 落 .tmp 临时目录、校验通过后 rename 进正式目录；
    成功后 .tmp 不留任何残留（R7）。"""
    skill_dir = git_cache.ensure_cached(
        registered_github_skill, upstream_repo.revision
    )

    assert (skill_dir / "SKILL.md").is_file()
    assert (roots.github_cache / "two-skills" / ".git").is_dir()
    assert git_cache.current_revision("two-skills") == upstream_repo.revision
    tmp_parent = roots.github_cache / ".tmp"
    assert tmp_parent.is_dir()
    assert not any(tmp_parent.iterdir())


def test_ensure_cached_keeps_existing_target_and_discards_tmp(
    git_cache, registered_github_skill, roots, upstream_repo
):
    """rename 前发现正式目录已存在（并发 clone 任务先行落地）：弃本次
    tmp、直接复用既有目录，绝不覆盖（design §3 双保险）。"""
    existing = roots.github_cache / "two-skills"
    skill_md_dir = existing / "skills" / "alpha"
    skill_md_dir.mkdir(parents=True)
    (skill_md_dir / "SKILL.md").write_text(
        "---\nname: pre-existing\n---\n", encoding="utf-8"
    )

    skill_dir = git_cache.ensure_cached(
        registered_github_skill, upstream_repo.revision
    )

    assert skill_dir == skill_md_dir.resolve()
    assert "pre-existing" in (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    # 既有目录未被 clone 结果覆盖
    assert not (existing / ".git").exists()
    assert not any((roots.github_cache / ".tmp").iterdir())


# ---------- 启动清理（PRD R8 / design §4，AC8） ----------


def test_cleanup_stale_workspaces_clears_scan_and_tmp_residue(settings, roots):
    """进程重启孤儿（扫描工作区 / clone 临时目录）在启动时被整体清空。"""
    stale_scan = roots.state / "scan" / "orphan-workspace"
    stale_scan.mkdir(parents=True)
    (stale_scan / "marker.txt").write_text("x", encoding="utf-8")
    stale_tmp = roots.github_cache / ".tmp" / "two-skills-deadbeef"
    stale_tmp.mkdir(parents=True)
    (stale_tmp / "marker.txt").write_text("x", encoding="utf-8")

    removed_scan, removed_tmp = cleanup_stale_workspaces(settings)

    assert (removed_scan, removed_tmp) == (1, 1)
    assert not any((roots.state / "scan").iterdir())
    assert not any((roots.github_cache / ".tmp").iterdir())


def test_cleanup_stale_workspaces_tolerates_missing_parents(settings, roots):
    """目录尚不存在（首次启动）时清理为 no-op，不报错。"""

    assert cleanup_stale_workspaces(settings) == (0, 0)

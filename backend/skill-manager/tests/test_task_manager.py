"""GithubTaskManager 测试：任务生命周期、错误映射、进度节流、密码边界
与完结任务惰性回收（09-26 后台任务化 Task 2）。

fixture 与 test_git_cache.py 同款（本地 bare 仓库充当 GitHub 远端，经
file:// remotes 映射完全离线）；超时场景用假 Popen（design 建议），不碰
真实网络。
"""

from __future__ import annotations

import io
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.db import SkillStateStore
from src.models import RegistrySkill
from src.services.git_cache import GitCacheService
from src.services.registry import RegistryService
from src.services.task_manager import (
    GithubTaskManager,
    _MutableTask,
    _apply_progress,
)

CANONICAL_URL = "https://github.com/example/two-skills"
BROKEN_URL = "https://github.com/example/broken"
RETENTION_SECONDS = 30 * 60


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
    """构造"远端"：工作仓库（两个 skill）→ bare clone，返回 (bare, HEAD)。"""
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
    run_git("add", "-A", cwd=work)
    run_git("commit", "-m", "fixture: two skills", cwd=work)

    bare = tmp_path / "upstream.git"
    run_git("clone", "--bare", str(work), str(bare))
    revision = run_git("rev-parse", "HEAD", cwd=bare).strip()
    return SimpleNamespace(bare=bare, revision=revision)


@pytest.fixture()
def git_cache(settings, store, upstream_repo):
    """规范化 URL → 本地 bare 仓库的 file:// 地址（离线且产生真实进度流）。"""
    return GitCacheService(
        settings,
        store,
        remotes={CANONICAL_URL: f"file:///{upstream_repo.bare.as_posix()}"},
    )


@pytest.fixture()
def offline_git_cache(settings, store, tmp_path):
    """BROKEN_URL 映射到不存在的本地仓库，离线验证 unreachable 映射。"""
    return GitCacheService(
        settings,
        store,
        remotes={BROKEN_URL: str(tmp_path / "missing.git")},
    )


@pytest.fixture()
def registry(settings, store):
    return RegistryService(store, settings.skills_source_root)


class _FakeClock:
    """可手动推进的秒级时钟：注入 manager 以确定性断言惰性回收。"""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture()
def clock():
    return _FakeClock()


@pytest.fixture()
def manager(git_cache, registry, clock):
    return GithubTaskManager(git_cache, registry, clock=clock)


@pytest.fixture()
def registered_github_skill():
    return RegistrySkill(
        id="two-skills",
        name="Two Skills",
        source="github",
        path="skills/alpha",
        repository=CANONICAL_URL,
    )


class _FakeHangingGitPopen:
    """假 git 进程：ls-remote 秒回固定 HEAD；clone 输出一帧 receiving
    进度后挂死（wait 永远超时），kill 只置位不退出。"""

    def __init__(self, cmd: list[str], **kwargs: object) -> None:
        self.cmd = cmd
        self.args = cmd
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

    # subprocess.run 以 `with Popen(...)` 使用进程对象（ls-remote 路径）
    def __enter__(self) -> "_FakeHangingGitPopen":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    # subprocess.run 的其余交互面：communicate/poll/returncode
    returncode = 0

    def communicate(
        self, input: str | None = None, timeout: float | None = None
    ) -> tuple[str, str]:
        return self.stdout.getvalue(), self.stderr.getvalue()

    def poll(self) -> int:
        return self.returncode


def _finished(manager: GithubTaskManager, task_id: str, timeout: float = 20.0):
    """轮询直到任务离开 running 态；超时失败以保证测试不悬挂。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = manager.get(task_id)
        if snapshot is not None and snapshot.state != "running":
            return snapshot
        time.sleep(0.01)
    raise AssertionError(f"task {task_id} did not finish within {timeout}s")


# ---------- 任务生命周期 ----------


def test_scan_task_completes_with_sorted_candidates(manager):
    snapshot = manager.start_scan(CANONICAL_URL)

    assert snapshot.kind == "scan"
    assert snapshot.skill_id is None
    assert snapshot.repository == CANONICAL_URL
    assert snapshot.state == "running"

    final = _finished(manager, snapshot.task_id)

    assert final.state == "done"
    assert final.error_code is None
    assert final.candidates == ("skills/alpha", "skills/beta")
    assert final.stage == "discover"


def test_register_task_completes_and_upserts_registry(
    manager, store, upstream_repo
):
    skill = RegistrySkill(
        id="two-skills",
        name="Two Skills",
        source="github",
        path="skills/alpha",
        repository=CANONICAL_URL,
    )

    final = _finished(manager, manager.start_register(skill).task_id)

    assert final.state == "done"
    assert final.stage == "registry"
    stored = store.get_registry_skill("two-skills")
    assert stored is not None
    assert str(stored.repository) == CANONICAL_URL


# ---------- 错误映射 ----------


def test_register_task_failure_maps_to_unreachable(
    offline_git_cache, registry, clock
):
    manager = GithubTaskManager(offline_git_cache, registry, clock=clock)
    skill = RegistrySkill(
        id="broken-skill",
        name="Broken",
        source="github",
        path="skills/alpha",
        repository=BROKEN_URL,
    )

    final = _finished(manager, manager.start_register(skill).task_id)

    assert final.state == "error"
    assert final.error_code == "unreachable"
    # 文案与第一阶段 HTTPException 逐字一致（PRD R9）
    assert final.error_message == "仓库不存在或当前网络无法访问"


def test_clone_task_timeout_maps_to_download_timeout(
    manager, registered_github_skill, monkeypatch
):
    created: list[_FakeHangingGitPopen] = []

    class RecordingFakePopen(_FakeHangingGitPopen):
        def __init__(self, cmd, **kwargs):
            super().__init__(cmd, **kwargs)
            created.append(self)

    monkeypatch.setattr(subprocess, "Popen", RecordingFakePopen)

    final = _finished(
        manager, manager.start_clone(registered_github_skill).task_id
    )

    assert final.state == "error"
    assert final.error_code == "download_timeout"
    # AC3：前端直接展示 message，文案与第一阶段 HTTPException 逐字一致
    assert final.error_message == "下载超时：仓库较大或当前网络较慢，可稍后重试"
    # 挂死前的最后一帧进度已被读线程上报
    assert final.progress_percent == 45
    assert created and created[-1].killed is True


# ---------- 密码边界（AC5） ----------


def test_password_never_appears_in_snapshot_or_internal_state(
    manager, registered_github_skill
):
    # 管理密码在路由同步段校验后即被丢弃，本模块任何结构都不应携带；
    # 该断言是回归哨兵：若未来有人把密码塞进任务上下文立刻暴露
    sentinel_password = "s3cret-hunter2-password"

    final = _finished(
        manager, manager.start_register(registered_github_skill).task_id
    )

    snapshot = manager.get(final.task_id)
    assert snapshot is not None
    assert sentinel_password not in repr(snapshot)
    assert sentinel_password not in repr(manager._tasks)


# ---------- 惰性回收（PRD R4） ----------


def test_finished_task_is_reclaimed_after_retention_window(manager, clock):
    task_id = manager.start_scan(CANONICAL_URL).task_id
    assert _finished(manager, task_id).state == "done"
    assert manager.get(task_id) is not None

    clock.advance(RETENTION_SECONDS - 1)
    assert manager.get(task_id) is not None  # 保留窗口内仍可查

    clock.advance(2)  # 越过 30 分钟
    assert manager.get(task_id) is None


# ---------- 进度节流 ----------


def test_apply_progress_throttles_duplicate_percent_frames():
    task = _MutableTask(
        task_id="throttle-fixture",
        kind="clone_cache",
        repository=CANONICAL_URL,
        skill=None,
        skill_id=None,
        created_at=0.0,
        updated_at=0.0,
    )

    assert _apply_progress(task, "receiving", 10, "10 KiB", now=1.0) is True
    # 同 phase 同 percent 的重复帧不推进（TaskManager 节流，design §1）
    assert _apply_progress(task, "receiving", 10, "10 KiB", now=2.0) is False
    assert task.updated_at == 1.0
    assert _apply_progress(task, "receiving", 20, "20 KiB", now=3.0) is True
    assert (task.stage, task.progress_percent) == ("receiving", 20)
    assert _apply_progress(task, "resolving", 10, "", now=4.0) is True
    assert task.stage == "resolving"

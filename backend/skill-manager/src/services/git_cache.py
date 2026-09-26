"""GitHub Skill 发现、更新检查与缓存 checkout（design 5 / Task 4）。

- URL 只接受规范化 `https://github.com/<owner>/<repo>`（可带 `.git` 后缀），
  file://、ssh://、其他主机（如 gitlab）一律 InvalidRepositoryError；
- `scan()` 以 `--depth 1` clone 到 `${SKILL_MANAGER_STATE_DIR}/scan/<uuid>`，
  递归扫描含 `SKILL.md` 的候选目录（忽略 `.git`、隐藏目录与工具目录），
  `finally` 中始终删除扫描工作区；
- `check_update()` 仅 `git ls-remote`（HEAD 与 `--tags --refs`），结果写
  github_check 记录（含失败记录），绝不 fetch/clone、绝不变更缓存内容；
- `ensure_cached()` 将仓库 clone/fetch 到
  `${GITHUB_SKILL_CACHE_ROOT}/<skill.id>` 并检出指定 revision，再校验登记
  路径内 `SKILL.md` 存在（缺失抛 CacheValidationError）；
- 全部 Git 调用为固定列表参数（shell=False、不接受外部拼接的命令片段）；
  clone 走流式执行器（`subprocess.Popen` + 读线程解析 `--progress` 进度，
  超时 kill），其余命令用 `subprocess.run`（capture_output + timeout）。

构造参数 `remotes` 是 URL→实际 Git URL 的映射，仅供离线测试注入本地
fixture 仓库；生产环境留空，Git 直接访问规范化后的 github.com 地址。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from src.config import Settings
from src.db import GithubCheckRecord, SkillStateStore
from src.models import RegistrySkill, ScanCandidate, SkillSource, UpdateInfo

# 单条 git 命令上限：clone 已全部改为后台任务（09-26 起），nginx 的 300s
# 代理读超时不再约束 git 时长；慢速出口（FastGithub 实测 ~51 KiB/s）下
# 十几 MB 仓库需 5-15 分钟，提升为 1800s（PRD R6）
_GIT_TIMEOUT_SECONDS = 1800
# clone 前可达性预检上限：ls-remote 仅元数据请求，正常秒回，超 30s 视为不可达
_REACHABILITY_TIMEOUT_SECONDS = 30
_SKILL_MD = "SKILL.md"
_SCAN_WORKSPACE_PARENT = "scan"
# 首次 clone 的临时目录父级：成功后整体 rename 进正式缓存目录（PRD R7）
_CLONE_TMP_PARENT = ".tmp"

# 规范化 github.com HTTPS 地址：owner 仅字母数字与连字符（不以连字符开头），
# repo 允许字母数字、连字符、下划线与点，`.git` 后缀与尾部斜杠被归一化
_GITHUB_HTTPS_RE = re.compile(
    r"^https://github\.com/"
    r"(?P<owner>[A-Za-z0-9][A-Za-z0-9-]*)/"
    r"(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)

# 仓库内扫描时按目录名排除的工具/缓存目录（隐藏目录统一按 "." 前缀排除），
# 与 registry.discover_local 的排除集合保持一致
_SCAN_EXCLUDED_DIRS = {"scripts", "__pycache__", "node_modules", "logs", "output"}

logger = logging.getLogger(__name__)


class GitCacheError(Exception):
    """GitHub 缓存域错误基类（API 层映射为 4xx）。"""


class InvalidRepositoryError(GitCacheError):
    """仓库 URL 不是规范化 github.com HTTPS 地址，或 skill 非 GitHub 来源。"""


class CacheValidationError(GitCacheError):
    """缓存内容校验失败：登记路径非法或不含 `SKILL.md`。"""


class GitOperationError(GitCacheError):
    """Git 命令执行失败（clone/fetch/checkout/ls-remote/rev-parse）。"""


class GitTimeoutError(GitOperationError):
    """Git 命令超时：仓库较大或网络较慢（API 层映射为 download_timeout）。"""


class UnreachableRepositoryError(GitCacheError):
    """clone 前可达性预检失败：仓库不存在或网络不可达（API 层映射为
    unreachable，避免等满 clone 超时才暴露）。"""


GitProgressPhase = Literal["negotiating", "receiving", "resolving"]


@dataclass(frozen=True)
class GitProgress:
    """`git clone --progress` stderr 的单帧解析结果（design §1）。

    negotiating（远端枚举/计数/压缩，`remote:` 前缀行）没有客户端侧
    百分比语义，percent 恒为 None；receiving/resolving 携带 0-100 的
    百分比与原始行尾明细（如 "22.27 KiB | 1.39 MiB/s, done."）。
    """

    phase: GitProgressPhase
    percent: int | None
    detail: str = ""


# 进度行形如 "Receiving objects:  45% (1589/3531) | 51.00 KiB/s"；
# 括号内 done/total 计数对前端无额外价值，只取百分比与行尾明细
_RECEIVING_PROGRESS_RE = re.compile(r"Receiving objects:\s+(\d+)%\s+\(\d+/\d+\)(.*)")
_RESOLVING_PROGRESS_RE = re.compile(r"Resolving deltas:\s+(\d+)%\s+\(\d+/\d+\)(.*)")


def _parse_progress_line(line: str) -> GitProgress | None:
    """把单行 stderr 解析为进度帧；非进度行（Cloning into、warning 等）
    返回 None。`remote:` 前缀行归为 negotiating（percent=None）。"""
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("remote:"):
        return GitProgress(
            phase="negotiating",
            percent=None,
            detail=stripped.removeprefix("remote:").strip(),
        )
    if (match := _RECEIVING_PROGRESS_RE.search(stripped)) is not None:
        return GitProgress("receiving", int(match[1]), match[2].strip())
    if (match := _RESOLVING_PROGRESS_RE.search(stripped)) is not None:
        return GitProgress("resolving", int(match[1]), match[2].strip())
    return None


class _ProgressLineSplitter:
    """按 \\r 与 \\n 两种分隔符切分 stderr 流并解析进度帧。

    git 以 \\r 覆盖刷新进度行，块读取会在任意字节处截断，因此残尾必须
    留在缓冲等下一块；流结束时 flush() 兜底解析最后的残尾。
    """

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, chunk: str) -> list[GitProgress]:
        self._buffer += chunk
        lines = re.split(r"[\r\n]", self._buffer)
        self._buffer = lines.pop()
        return [
            frame
            for line in lines
            if (frame := _parse_progress_line(line)) is not None
        ]

    def flush(self) -> list[GitProgress]:
        remainder, self._buffer = self._buffer, ""
        if not remainder:
            return []
        frame = _parse_progress_line(remainder)
        return [frame] if frame is not None else []


def _drain_text_stream(stream, chunks: list[str]) -> None:
    """读线程体：把文本流 drain 进 chunks（进程退出/管道关闭时结束）。"""
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        chunks.append(chunk)


def _consume_progress_stream(
    stream,
    chunks: list[str],
    splitter: _ProgressLineSplitter,
    on_progress: Callable[[GitProgress], None],
) -> None:
    """读线程体：drain stderr、累积原文并逐帧上报解析出的进度。"""
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        chunks.append(chunk)
        try:
            for frame in splitter.feed(chunk):
                on_progress(frame)
        except Exception:
            # 进度回调异常不得让读线程静默死亡（管道堆积会卡死 git）；
            # 记日志后继续读
            logger.exception("progress callback failed")
    try:
        for frame in splitter.flush():
            on_progress(frame)
    except Exception:
        logger.exception("progress callback failed")


def _ignore_progress(frame: GitProgress) -> None:
    """无回调时的进度丢弃桩。"""
    return None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _force_remove(func, path, exc_info) -> None:
    """`shutil.rmtree` onexc 处理器：Windows 上 git 对象文件带只读位，
    先清除只读位再重试删除。"""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _remove_workspace(workspace: Path) -> None:
    try:
        shutil.rmtree(workspace, onexc=_force_remove)
    except OSError:
        # 清理失败不得掩盖 scan/clone 的原始结果；残留仅限进程内临时目录
        # （state/scan 工作区或 .tmp clone 临时目录，启动清理兜底）
        pass


def cleanup_stale_workspaces(settings: Settings) -> tuple[int, int]:
    """清空进程重启遗留的扫描工作区与 clone 临时目录（PRD R8 / design §4）。

    `state/scan/*` 扫描工作区与 `GITHUB_SKILL_CACHE_ROOT/.tmp/*` clone
    临时目录都是进程内短生命周期目录：任务随进程消失，残留即孤儿，启动时
    整体清空（不存在"残留仍被运行中任务使用"的窗口——进程都重启了）。
    返回 (清理的 scan 目录数, 清理的 tmp 目录数)；单项失败只记日志，
    绝不阻断启动。
    """
    removed_scan = _clear_directory_children(
        settings.state_dir / _SCAN_WORKSPACE_PARENT
    )
    removed_tmp = _clear_directory_children(
        settings.github_skill_cache_root / _CLONE_TMP_PARENT
    )
    logger.info(
        "startup cleanup: removed %d stale scan workspaces, %d stale clone tmp dirs",
        removed_scan,
        removed_tmp,
    )
    return removed_scan, removed_tmp


def _clear_directory_children(parent: Path) -> int:
    """删除 parent 下全部子项，返回成功删除数；parent 不存在返回 0。"""
    if not parent.is_dir():
        return 0
    removed = 0
    for child in parent.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, onexc=_force_remove)
            else:
                child.unlink()
        except OSError:
            logger.warning("startup cleanup failed to remove %s", child)
            continue
        removed += 1
    return removed


class GitCacheService:
    """以 Settings 固定目录为边界的 GitHub Skill 缓存服务。"""

    def __init__(
        self,
        settings: Settings,
        store: SkillStateStore,
        remotes: Mapping[str, str] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        # 仅测试注入的 URL→实际 Git URL 映射；生产恒等返回（见 _remote_for）
        self._remotes: Mapping[str, str] = dict(remotes or {})

    # ---------- URL 规范化 ----------

    def normalize_repository(self, url: str) -> str:
        """把可接受的 GitHub HTTPS URL 规范化为 `https://github.com/<owner>/<repo>`。"""
        match = _GITHUB_HTTPS_RE.match(url.strip())
        if match is None or match["repo"] in {".", ".."}:
            # repo 段拒绝 "."/".."：纯点段是路径语义特殊段，防止 URL 拼接歧义
            raise InvalidRepositoryError(
                f"only normalized https://github.com/<owner>/<repo> URLs are "
                f"accepted, got: {url!r}"
            )
        return f"https://github.com/{match['owner']}/{match['repo']}"

    # ---------- 扫描 ----------

    def verify_reachable(self, canonical_url: str) -> None:
        """clone 前的快速可达性检查（ls-remote HEAD，≤30s）。

        元数据请求正常秒回；失败或超时说明仓库不存在或网络不可达，
        让调用方在发起全量 clone 之前就拿到明确错误。
        """
        try:
            self._run_git(
                ["ls-remote", self._remote_for(canonical_url), "HEAD"],
                timeout=_REACHABILITY_TIMEOUT_SECONDS,
            )
        except GitOperationError as exc:
            raise UnreachableRepositoryError(
                f"repository {canonical_url} is unreachable: {exc}"
            ) from exc

    def scan(
        self,
        repository_url: str,
        on_progress: Callable[[GitProgress], None] | None = None,
    ) -> list[ScanCandidate]:
        """临时 clone 并扫描含 `SKILL.md` 的候选目录；工作区始终清理。

        统一走流式执行器 + `--progress`（design §1）：有回调时进度实时
        上报，无回调时进度仅被丢弃。
        """
        canonical = self.normalize_repository(repository_url)
        workspace_parent = self.settings.state_dir / _SCAN_WORKSPACE_PARENT
        workspace_parent.mkdir(parents=True, exist_ok=True)
        workspace = workspace_parent / uuid.uuid4().hex
        try:
            self._run_git_streaming(
                [
                    "clone",
                    "--depth",
                    "1",
                    "--progress",
                    self._remote_for(canonical),
                    str(workspace),
                ],
                on_progress or _ignore_progress,
            )
            return self._discover_candidates(workspace)
        finally:
            _remove_workspace(workspace)

    # ---------- 更新检查（只读） ----------

    def check_update(self, skill: RegistrySkill) -> UpdateInfo:
        """仅 ls-remote 获取远端 HEAD 与 tags，写 github_check，不动缓存。"""
        canonical = self._require_github_skill(skill)
        remote = self._remote_for(canonical)
        try:
            head = self._ls_remote_head(remote)
            tags = self._ls_remote_tags(remote)
        except GitOperationError as exc:
            self._record_check_failure(skill, canonical, exc)
            raise
        cached_revision = self.current_revision(skill.id)
        info = UpdateInfo(
            skill_id=skill.id,
            repository=canonical,
            remote_revision=head,
            remote_tags=tags,
            cached_revision=cached_revision,
            has_update=head != cached_revision,
            checked_at=_utc_now_iso(),
        )
        self._record_check_success(skill, canonical, info)
        return info

    # ---------- 缓存 checkout ----------

    def ensure_cached(
        self,
        skill: RegistrySkill,
        revision: str,
        on_progress: Callable[[GitProgress], None] | None = None,
    ) -> Path:
        """把仓库同步到缓存并检出指定 revision，返回含 `SKILL.md` 的登记目录。

        已有缓存（含 `.git`）走 fetch 更新，路径不变；首次 clone 先落
        `.tmp/<skill.id>-<uuid>` 临时目录，checkout 与 SKILL.md 校验通过后
        原子 rename 进正式目录（PRD R7）：clone 中断/失败不留半成品缓存，
        `finally` 始终清理本次 tmp，进程级残留由启动清理兜底（design §4）。
        rename 前发现正式目录已存在（并发 clone 任务先行落地）则弃本次
        tmp、直接复用既有目录（design §3 双保险）。clone 统一走流式执行器
        以实时上报下载进度（design §1）。
        """
        canonical = self._require_github_skill(skill)
        self._require_safe_relative_path(skill)
        cache_dir = self.settings.github_skill_cache_root / skill.id
        # 快速失败：缓存已存在但登记路径不含 SKILL.md，无需任何 Git 操作
        self._check_registered_path_present(skill, cache_dir)
        if (cache_dir / ".git").is_dir():
            self._run_git(["fetch", "--force", "--tags"], cwd=cache_dir)
            self._run_git(["checkout", "--force", revision], cwd=cache_dir)
            return self._validated_skill_dir(skill, cache_dir)
        tmp_parent = self.settings.github_skill_cache_root / _CLONE_TMP_PARENT
        tmp_parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = tmp_parent / f"{skill.id}-{uuid.uuid4().hex}"
        try:
            self._run_git_streaming(
                [
                    "clone",
                    "--progress",
                    self._remote_for(canonical),
                    str(tmp_dir),
                ],
                on_progress or _ignore_progress,
            )
            self._run_git(["checkout", "--force", revision], cwd=tmp_dir)
            self._validated_skill_dir(skill, tmp_dir)
            if cache_dir.exists():
                # 并发双保险：另一 clone 任务在本次 clone 期间把正式目录
                # 落了地（该方法开头已对既有目录做过 SKILL.md 校验）
                return self._validated_skill_dir(skill, cache_dir)
            # 同盘 rename：要么完整落地要么不存在，无中间态
            tmp_dir.replace(cache_dir)
        finally:
            _remove_workspace(tmp_dir)
        return self._validated_skill_dir(skill, cache_dir)

    def current_revision(self, skill_id: str) -> str:
        """读取缓存当前 HEAD；缓存不存在返回空串。"""
        cache_dir = self.settings.github_skill_cache_root / skill_id
        if not (cache_dir / ".git").is_dir():
            return ""
        return self._run_git(["rev-parse", "HEAD"], cwd=cache_dir).strip()

    # ---------- 内部：git 执行 ----------

    def _run_git(
        self,
        argv: list[str],
        cwd: Path | None = None,
        timeout: int = _GIT_TIMEOUT_SECONDS,
    ) -> str:
        """运行固定列表参数的 git 命令，返回 stdout；失败统一包装。"""
        try:
            completed = subprocess.run(
                ["git", *argv],
                cwd=cwd,
                shell=False,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr if isinstance(exc.stderr, str) else ""
            raise GitOperationError(
                f"git {argv[0]} failed: {detail.strip()}"
            ) from exc
        except FileNotFoundError as exc:
            # 运行环境没有 git 二进制（如镜像漏装）：包装成域错误，
            # 让 API 层表达为 400 而非未捕获异常的 500
            raise GitOperationError(
                f"git {argv[0]} unavailable: git is not installed in this "
                f"runtime environment"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise GitTimeoutError(
                f"git {argv[0]} timed out after {timeout} seconds"
            ) from exc
        return completed.stdout

    def _run_git_streaming(
        self,
        argv: list[str],
        on_progress: Callable[[GitProgress], None],
        cwd: Path | None = None,
        timeout: int = _GIT_TIMEOUT_SECONDS,
    ) -> str:
        """运行 git 命令并流式解析 stderr 的 `--progress` 输出（design §1）。

        超时模型（Windows 上 select 对管道不可移植）：stdout/stderr 各由
        一个读线程 drain，主线程 `wait(remaining)` 到点即 kill 进程并抛
        GitTimeoutError；读线程在管道关闭后随即退出。返回 stdout；非零
        退出以完整 stderr 拼 GitOperationError（与 `_run_git` 同语义）。
        """
        try:
            process = subprocess.Popen(
                ["git", *argv],
                cwd=cwd,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            # 运行环境没有 git 二进制（如镜像漏装）：与 _run_git 同口径包装
            raise GitOperationError(
                f"git {argv[0]} unavailable: git is not installed in this "
                f"runtime environment"
            ) from exc
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        stdout_thread = threading.Thread(
            target=_drain_text_stream,
            args=(process.stdout, stdout_chunks),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_consume_progress_stream,
            args=(
                process.stderr,
                stderr_chunks,
                _ProgressLineSplitter(),
                on_progress,
            ),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        deadline = time.monotonic() + timeout
        try:
            exit_code = process.wait(
                timeout=max(deadline - time.monotonic(), 0.001)
            )
        except subprocess.TimeoutExpired as exc:
            process.kill()
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            raise GitTimeoutError(
                f"git {argv[0]} timed out after {timeout} seconds"
            ) from exc
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        if exit_code != 0:
            raise GitOperationError(
                f"git {argv[0]} failed: {''.join(stderr_chunks).strip()}"
            )
        return "".join(stdout_chunks)

    def _remote_for(self, canonical_url: str) -> str:
        """生产恒等返回规范化 URL；测试经 remotes 映射指向离线 fixture 仓库。"""
        return self._remotes.get(canonical_url, canonical_url)

    def _ls_remote_head(self, remote: str) -> str:
        output = self._run_git(["ls-remote", remote, "HEAD"])
        for line in output.splitlines():
            sha, _, ref = line.partition("\t")
            if ref.strip() == "HEAD":
                return sha.strip()
        raise GitOperationError(f"remote {remote} did not report HEAD")

    def _ls_remote_tags(self, remote: str) -> list[str]:
        output = self._run_git(["ls-remote", "--tags", "--refs", remote])
        tags = [
            ref.strip().removeprefix("refs/tags/")
            for line in output.splitlines()
            if (ref := line.partition("\t")[2]).strip().startswith("refs/tags/")
        ]
        return sorted(tags)

    # ---------- 内部：校验 ----------

    def _require_github_skill(self, skill: RegistrySkill) -> str:
        if skill.source is not SkillSource.GITHUB or skill.repository is None:
            raise InvalidRepositoryError(
                f"skill {skill.id!r} is not a registered github skill"
            )
        return self.normalize_repository(str(skill.repository))

    def _require_safe_relative_path(self, skill: RegistrySkill) -> None:
        relative = Path(skill.path)
        if relative.is_absolute() or ".." in relative.parts:
            raise CacheValidationError(
                f"github skill path {skill.path!r} must be a relative subdirectory"
            )

    def _check_registered_path_present(
        self, skill: RegistrySkill, cache_dir: Path
    ) -> None:
        """缓存目录存在时校验登记路径含 `SKILL.md`；缓存不存在则跳过。"""
        if not cache_dir.is_dir():
            return
        self._validated_skill_dir(skill, cache_dir)

    def _validated_skill_dir(self, skill: RegistrySkill, cache_dir: Path) -> Path:
        skill_dir = (cache_dir / skill.path).resolve()
        if not (skill_dir / _SKILL_MD).is_file():
            raise CacheValidationError(
                f"cached skill {skill.id!r}: registered path {skill.path!r} "
                f"does not contain SKILL.md"
            )
        return skill_dir

    # ---------- 内部：扫描与记录 ----------

    def _discover_candidates(self, workspace: Path) -> list[ScanCandidate]:
        candidates: list[ScanCandidate] = []
        for dirpath, dirnames, filenames in os.walk(workspace):
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith(".") and d not in _SCAN_EXCLUDED_DIRS
            ]
            if _SKILL_MD not in filenames:
                continue
            candidates.append(
                ScanCandidate(path=Path(dirpath).relative_to(workspace).as_posix())
            )
        candidates.sort(key=lambda candidate: candidate.path)
        return candidates

    def _record_check_success(
        self, skill: RegistrySkill, canonical: str, info: UpdateInfo
    ) -> None:
        self.store.upsert_github_check(
            GithubCheckRecord(
                skill_id=info.skill_id,
                repository=canonical,
                remote_revision=info.remote_revision,
                remote_tags=",".join(info.remote_tags),
                cached_revision=info.cached_revision,
                result="ok",
                error=None,
                checked_at=info.checked_at,
            )
        )

    def _record_check_failure(
        self, skill: RegistrySkill, canonical: str, exc: GitOperationError
    ) -> None:
        self.store.upsert_github_check(
            GithubCheckRecord(
                skill_id=skill.id,
                repository=canonical,
                remote_revision="",
                remote_tags="",
                cached_revision="",
                result="error",
                error=str(exc),
                checked_at=_utc_now_iso(),
            )
        )

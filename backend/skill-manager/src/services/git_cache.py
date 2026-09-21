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
- 全部 Git 调用为固定列表参数（`subprocess.run`，shell=False、check=True、
  timeout），不接受外部拼接的命令片段。

构造参数 `remotes` 是 URL→实际 Git URL 的映射，仅供离线测试注入本地
fixture 仓库；生产环境留空，Git 直接访问规范化后的 github.com 地址。
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from src.config import Settings
from src.db import GithubCheckRecord, SkillStateStore
from src.models import RegistrySkill, ScanCandidate, SkillSource, UpdateInfo

_GIT_TIMEOUT_SECONDS = 60
_SKILL_MD = "SKILL.md"
_SCAN_WORKSPACE_PARENT = "scan"

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


class GitCacheError(Exception):
    """GitHub 缓存域错误基类（API 层映射为 4xx）。"""


class InvalidRepositoryError(GitCacheError):
    """仓库 URL 不是规范化 github.com HTTPS 地址，或 skill 非 GitHub 来源。"""


class CacheValidationError(GitCacheError):
    """缓存内容校验失败：登记路径非法或不含 `SKILL.md`。"""


class GitOperationError(GitCacheError):
    """Git 命令执行失败（clone/fetch/checkout/ls-remote/rev-parse）。"""


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
        # 清理失败不得掩盖 scan 的原始结果；残留仅限 state/scan 临时目录
        pass


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

    def scan(self, repository_url: str) -> list[ScanCandidate]:
        """临时 clone 并扫描含 `SKILL.md` 的候选目录；工作区始终清理。"""
        canonical = self.normalize_repository(repository_url)
        workspace_parent = self.settings.state_dir / _SCAN_WORKSPACE_PARENT
        workspace_parent.mkdir(parents=True, exist_ok=True)
        workspace = workspace_parent / uuid.uuid4().hex
        try:
            self._run_git(
                ["clone", "--depth", "1", self._remote_for(canonical), str(workspace)]
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

    def ensure_cached(self, skill: RegistrySkill, revision: str) -> Path:
        """把仓库同步到缓存并检出指定 revision，返回含 `SKILL.md` 的登记目录。

        已有缓存且登记路径缺失时直接失败（不发起任何 Git 操作）；checkout
        之后再做权威校验，防止目标 revision 中目录被删除。
        """
        canonical = self._require_github_skill(skill)
        self._require_safe_relative_path(skill)
        cache_dir = self.settings.github_skill_cache_root / skill.id
        # 快速失败：缓存已存在但登记路径不含 SKILL.md，无需任何 Git 操作
        self._check_registered_path_present(skill, cache_dir)
        if (cache_dir / ".git").is_dir():
            self._run_git(["fetch", "--force", "--tags"], cwd=cache_dir)
        else:
            self._run_git(["clone", self._remote_for(canonical), str(cache_dir)])
        self._run_git(["checkout", "--force", revision], cwd=cache_dir)
        return self._validated_skill_dir(skill, cache_dir)

    def current_revision(self, skill_id: str) -> str:
        """读取缓存当前 HEAD；缓存不存在返回空串。"""
        cache_dir = self.settings.github_skill_cache_root / skill_id
        if not (cache_dir / ".git").is_dir():
            return ""
        return self._run_git(["rev-parse", "HEAD"], cwd=cache_dir).strip()

    # ---------- 内部：git 执行 ----------

    def _run_git(self, argv: list[str], cwd: Path | None = None) -> str:
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
                timeout=_GIT_TIMEOUT_SECONDS,
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
            raise GitOperationError(f"git {argv[0]} timed out") from exc
        return completed.stdout

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

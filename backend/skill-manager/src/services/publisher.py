"""受限目录内的安全发布与下架（design 6.1）。

发布算法（每一项 skill × target，见 design 6.1）：

1. 校验 skill id 与源目录（存在、含 `SKILL.md`、resolve 后位于受控源根
   ——源库根或 GitHub 缓存根——之内）；
2. 目标链接固定为 `${TARGET_ROOT}/${skill-id}`；target 只能是 TargetKey
   枚举映射的固定目录；已有普通目录/文件或指向受控根之外的链接一律拒绝；
3. 同目录创建临时 symlink `.{skill_id}.{uuid}.next`，验证其解析到源；
4. 用 `os.replace` 原子替换正式链接（同目录 rename，原子生效）；
5. 写 deployment / deployment_history。单项失败只记录该项，临时链接在
   finally 中清理，绝不触碰其他 Skill。

GitHub 条目的发布源是 **staging 目录**（2026-09-30 批量登记任务）：
`stage_github_skill()` 在 `${GITHUB_SKILL_CACHE_ROOT}/staging/<skill-id>/
<short-rev>/` 组装「skill 子目录 + shared_paths 随行资源」的拷贝快照，
symlink 指向该 rev 目录。rev 目录使每次发布都是独立快照：后续共享缓存
checkout 到其他 revision 不影响已发布内容，且 symlink 原子切换零悬空
窗口；每个 skill 仅保留最新 2 个 rev 目录，更旧的自动清理。

注：回滚功能已整体移除（2026-09-23）——发布链接在两种来源下均指向稳定
路径，快照机制对其声称的「退回旧版」场景无效，详见任务
09-23-skill-manager-remove-rollback 的 PRD。
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from src.config import Settings
from src.db import DeploymentRecord, HistoryEntry, SkillStateStore
from src.models import (
    SKILL_ID_PATTERN,
    PublishBatchResult,
    PublishItem,
    PublishResultItem,
    RegistrySkill,
    SkillSource,
    TargetKey,
    target_kind,
)

_ID_RE = re.compile(SKILL_ID_PATTERN)
_SKILL_MD = "SKILL.md"
_TEMP_LINK_SUFFIX = ".next"
# staging 布局：cache_root/staging/<skill-id>/<short-rev>/
_STAGING_PARENT = "staging"
# short rev 目录名长度：git 默认短 sha 为 7+ 自适应，12 位碰撞概率可忽略
_REV_DIR_LENGTH = 12
# 每个 skill 保留的 staging rev 目录数（最新 N 份）
_STAGING_KEEP_REVS = 2
# 组装 staging 时忽略的目录（.git 绝不进发布产物）
_STAGING_IGNORE = shutil.ignore_patterns(".git")


class PublisherError(Exception):
    """发布域错误基类（API 层映射为 4xx / 批量逐项结果）。"""


class InvalidSourceError(PublisherError):
    """源侧校验失败：非法 id、源缺失、缺 SKILL.md 或越出受控根（400 语义）。"""


class PublishBlockedError(PublisherError):
    """目标侧阻止：普通目录占用、异常链接等；未做任何文件系统变更。"""


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def validated_source(settings: Settings, source: Path) -> Path:
    """把任意候选源目录校验为受控源；返回 resolve 后的绝对路径。

    规则（design 6.1 第 1 步）：目录存在、含 `SKILL.md`、resolve 后位于
    源库根或 GitHub 缓存根之内。Publisher 与 API plan/publish 端点共用。
    """
    resolved = Path(source).resolve()
    if not resolved.is_dir():
        raise InvalidSourceError(f"source directory does not exist: {resolved}")
    if not (resolved / _SKILL_MD).is_file():
        raise InvalidSourceError(
            f"source directory {resolved} does not contain SKILL.md"
        )
    if not _inside_controlled_roots(settings, resolved):
        raise InvalidSourceError(
            f"source {resolved} is outside the controlled roots "
            f"({settings.skills_source_root}, {settings.github_skill_cache_root})"
        )
    return resolved


def resolve_registry_source(settings: Settings, skill: RegistrySkill) -> Path:
    """把 local 注册表条目解析为受控源目录；无效时抛 InvalidSourceError。

    仅服务 local 条目（源库目录直链）；github 条目的发布源是 staging
    快照（`Publisher.stage_github_skill`），计划预览用
    `Publisher.planned_staging_dir` 只读计算。
    """
    if skill.source is not SkillSource.LOCAL:
        raise InvalidSourceError(
            f"github skill {skill.id!r} resolves via staging, not direct source"
        )
    candidate = (settings.skills_source_root / skill.path).resolve()
    return validated_source(settings, candidate)


def _force_remove_tree(func, path, exc_info) -> None:
    """`shutil.rmtree` onexc 处理器：Windows 上只读位文件先清位再删。"""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def force_remove_tree(path: Path) -> None:
    """删除目录树（跨模块复用：routes 删缓存 / migration 搬旧缓存）。"""
    shutil.rmtree(path, onexc=_force_remove_tree)


def _inside_controlled_roots(settings: Settings, resolved: Path) -> bool:
    return resolved.is_relative_to(
        settings.skills_source_root
    ) or resolved.is_relative_to(settings.github_skill_cache_root)


class Publisher:
    """以 Settings 中固定目标目录为唯一写入边界的发布服务。"""

    def __init__(self, settings: Settings, store: SkillStateStore) -> None:
        self.settings = settings
        self.store = store

    # ---------- staging（github 条目发布快照） ----------

    def staging_root(self) -> Path:
        """staging 根：cache root 下，天然落在受控根边界内（design §4.1）。"""
        return self.settings.github_skill_cache_root / _STAGING_PARENT

    def planned_staging_dir(self, skill_id: str, revision: str) -> Path:
        """只读计算某 skill 在指定 revision 下的 staging 目录（不组装）。"""
        rev_dir = revision[:_REV_DIR_LENGTH] if revision else "uncached"
        return self.staging_root() / skill_id / rev_dir

    def stage_github_skill(
        self, skill: RegistrySkill, revision: str, repo_dir: Path
    ) -> Path:
        """组装 github 条目的 staging rev 目录，返回该目录作为发布链接目标。

        - `repo_dir` 是共享缓存仓库目录（含 `.git` 与检出内容），必须在
          GitHub 缓存根之内；skill 登记路径必须含 `SKILL.md`；
        - 组装顺序：先 `shared_paths` 随行资源、后 skill 本体（本体覆盖
          同名文件）；`.git` 永不进入产物；
        - 组装落 `.tmp` 后原子 rename；同 rev 目录已存在（重复发布）直接
          复用；完成后清理过期 rev，仅保留最新 `_STAGING_KEEP_REVS` 份。
        """
        resolved_repo = repo_dir.resolve()
        if not resolved_repo.is_relative_to(self.settings.github_skill_cache_root):
            raise InvalidSourceError(
                f"repository cache {repo_dir} is outside the GitHub cache root"
            )
        skill_dir = (resolved_repo / skill.path).resolve()
        if not (skill_dir / _SKILL_MD).is_file():
            raise InvalidSourceError(
                f"cached skill {skill.id!r} path {skill.path!r} does not "
                f"contain SKILL.md"
            )
        rev_dir = revision[:_REV_DIR_LENGTH] if revision else "uncached"
        final_dir = self.staging_root() / skill.id / rev_dir
        if final_dir.is_dir():
            self._cleanup_stale_revs(skill.id)
            return final_dir
        tmp_dir = (
            self.staging_root()
            / f".{skill.id}.{uuid.uuid4().hex}{_TEMP_LINK_SUFFIX}"
        )
        tmp_dir.mkdir(parents=True, exist_ok=True)
        # rev 目录的父目录（staging/<skill-id>/）首次组装时创建
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            for shared in skill.shared_paths:
                shared_src = (resolved_repo / shared).resolve()
                if not shared_src.exists():
                    raise PublishBlockedError(
                        f"shared path {shared!r} does not exist in repository "
                        f"{str(skill.repository)}"
                    )
                if not shared_src.is_relative_to(resolved_repo):
                    raise PublishBlockedError(
                        f"shared path {shared!r} escapes the repository root"
                    )
                shared_dst = tmp_dir / shared
                shared_dst.parent.mkdir(parents=True, exist_ok=True)
                if shared_src.is_dir():
                    shutil.copytree(
                        shared_src, shared_dst, ignore=_STAGING_IGNORE
                    )
                else:
                    shutil.copy2(shared_src, shared_dst)
            shutil.copytree(
                skill_dir, tmp_dir, ignore=_STAGING_IGNORE, dirs_exist_ok=True
            )
            if final_dir.exists():
                # 并发组装先行落地：弃本次 tmp，复用既有目录
                return final_dir
            tmp_dir.replace(final_dir)
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, onexc=_force_remove_tree)
        self._cleanup_stale_revs(skill.id)
        return final_dir

    def _cleanup_stale_revs(self, skill_id: str) -> None:
        """删除超过保留数的旧 staging rev 目录（按 mtime 取最新 N 份）。

        mtime 用 ns 精度（`st_mtime_ns`）；文件系统时间戳粒度更粗时同刻
        目录的取舍不确定，但真实发布间隔远大于时间戳粒度，可忽略。
        """
        skill_staging = self.staging_root() / skill_id
        if not skill_staging.is_dir():
            return
        rev_dirs = [d for d in skill_staging.iterdir() if d.is_dir()]
        rev_dirs.sort(key=lambda d: d.stat().st_mtime_ns, reverse=True)
        for stale in rev_dirs[_STAGING_KEEP_REVS:]:
            shutil.rmtree(stale, onexc=_force_remove_tree)

    def remove_staging(self, skill_id: str) -> None:
        """删除某 skill 的全部 staging rev 目录（删除登记时清理，尽力而为）。"""
        skill_staging = self.staging_root() / skill_id
        if skill_staging.is_dir():
            shutil.rmtree(skill_staging, onexc=_force_remove_tree)

    # ---------- 发布 ----------

    def publish(
        self, skill_id: str, target: TargetKey, source: Path, revision: str = ""
    ) -> PublishResultItem:
        self._require_valid_id(skill_id)
        resolved_source = self._validated_source(source)
        try:
            action, previous = self._atomic_swap(skill_id, target, resolved_source)
        except PublishBlockedError as exc:
            self._record_failure(skill_id, target, "publish", "blocked", exc, revision)
            raise
        except PublisherError as exc:
            self._record_failure(skill_id, target, "publish", "error", exc, revision)
            raise
        self._persist_active(skill_id, target, resolved_source, revision)
        self.store.append_history(
            HistoryEntry(
                skill_id=skill_id,
                target=target.value,
                action="publish",
                result="success",
                previous_link_target=previous,
                new_link_target=str(resolved_source),
                source_revision=revision,
                error=None,
                created_at=_utc_now_iso(),
            )
        )
        return PublishResultItem(
            skill_id=skill_id, target=target, status="success", action=action
        )

    def publish_many(self, items: Sequence[PublishItem]) -> PublishBatchResult:
        """逐项独立执行；单项失败记 blocked/error，不影响其他项（design 6.1）。"""
        return PublishBatchResult(items=[self._publish_one(item) for item in items])

    # ---------- 下架 ----------

    def unpublish(self, skill_id: str, target: TargetKey) -> None:
        """只删除受管 symlink 本身；普通目录、越界链接一律拒绝，绝不 rmtree。"""
        self._require_valid_id(skill_id)
        final_link = self._target_root(target) / skill_id
        previous: str
        try:
            if final_link.is_symlink():
                resolved = final_link.resolve()
                if not _inside_controlled_roots(self.settings, resolved):
                    raise PublishBlockedError(
                        f"existing link {final_link} points outside the controlled "
                        f"roots ({resolved}); refusing to delete it"
                    )
                previous = str(resolved)
            elif final_link.exists():
                raise PublishBlockedError(
                    f"target {final_link} is an ordinary directory or file; "
                    f"refusing to delete it"
                )
            else:
                raise PublishBlockedError(
                    f"no managed symlink for skill {skill_id!r} on {target.value!r}"
                )
        except PublishBlockedError as exc:
            self._record_failure(skill_id, target, "unpublish", "blocked", exc)
            raise
        existing = self.store.get_deployment(skill_id, target.value)
        final_link.unlink()
        self.store.upsert_deployment(
            DeploymentRecord(
                skill_id=skill_id,
                target=target.value,
                source_revision=existing.source_revision if existing else "",
                source_path=existing.source_path if existing else "",
                current_link_target="",
                status="removed",
                published_at=_utc_now_iso(),
            )
        )
        self.store.append_history(
            HistoryEntry(
                skill_id=skill_id,
                target=target.value,
                action="unpublish",
                result="success",
                previous_link_target=previous,
                new_link_target=None,
                source_revision=existing.source_revision if existing else "",
                error=None,
                created_at=_utc_now_iso(),
            )
        )

    # ---------- 内部：核心交换流程 ----------

    def _atomic_swap(
        self, skill_id: str, target: TargetKey, resolved_source: Path
    ) -> tuple[str, str | None]:
        """design 6.1 第 2-4 步：检查现有链接 → 临时链接验证 → 原子替换。

        返回 (action, 替换前解析目标)；action 为 "add" 或 "update"。
        """
        target_root = self._target_root(target)
        final_link = target_root / skill_id
        action = self._inspect_existing_link(final_link)
        previous = str(final_link.resolve()) if action == "update" else None
        temp_link = target_root / f".{skill_id}.{uuid.uuid4().hex}{_TEMP_LINK_SUFFIX}"
        try:
            try:
                temp_link.symlink_to(resolved_source, target_is_directory=True)
                if temp_link.resolve() != resolved_source:
                    raise PublisherError(
                        f"temporary link {temp_link} does not resolve to "
                        f"{resolved_source}"
                    )
                os.replace(temp_link, final_link)
            except OSError as exc:
                # 文件系统层失败统一包装为发布域错误，供批量结果与 API 层表达
                raise PublisherError(
                    f"filesystem operation failed: {exc}"
                ) from exc
        finally:
            if temp_link.is_symlink():
                temp_link.unlink()
        return action, previous

    def _inspect_existing_link(self, final_link: Path) -> str:
        """分类现有目标：add（不存在）/ update（受管 symlink）/ 拒绝。"""
        if final_link.is_symlink():
            resolved = final_link.resolve()
            if not _inside_controlled_roots(self.settings, resolved):
                raise PublishBlockedError(
                    f"existing link {final_link} points outside the controlled "
                    f"roots ({resolved}); refusing to touch it"
                )
            return "update"
        if final_link.exists():
            raise PublishBlockedError(
                f"target {final_link} is an ordinary directory or file; "
                f"refusing to overwrite it"
            )
        return "add"

    # ---------- 内部：校验与边界 ----------

    def _target_root(self, target: TargetKey) -> Path:
        if target_kind(target) != "link":
            raise PublishBlockedError("外部目标用导出，不走发布")
        roots = {
            TargetKey.OPENCLAW: self.settings.openclaw_skills_root,
            TargetKey.HERMES: self.settings.hermes_skills_root,
        }
        return roots[target]

    def _require_valid_id(self, skill_id: str) -> None:
        if not _ID_RE.match(skill_id):
            raise InvalidSourceError(f"invalid skill id: {skill_id!r}")

    def _validated_source(self, source: Path | str) -> Path:
        return validated_source(self.settings, Path(source))

    # ---------- 内部：状态持久化 ----------

    def _persist_active(
        self, skill_id: str, target: TargetKey, resolved_source: Path, revision: str
    ) -> None:
        self.store.upsert_deployment(
            DeploymentRecord(
                skill_id=skill_id,
                target=target.value,
                source_revision=revision,
                source_path=str(resolved_source),
                current_link_target=str(resolved_source),
                status="active",
                published_at=_utc_now_iso(),
            )
        )

    def _record_failure(
        self,
        skill_id: str,
        target: TargetKey,
        action: str,
        result: str,
        exc: PublisherError,
        revision: str = "",
    ) -> None:
        self.store.append_history(
            HistoryEntry(
                skill_id=skill_id,
                target=target.value,
                action=action,
                result=result,
                previous_link_target=None,
                new_link_target=None,
                source_revision=revision,
                error=str(exc),
                created_at=_utc_now_iso(),
            )
        )

    def _publish_one(self, item: PublishItem) -> PublishResultItem:
        try:
            return self.publish(item.skill_id, item.target, item.source, item.revision)
        except PublishBlockedError as exc:
            return PublishResultItem(
                skill_id=item.skill_id, target=item.target, status="blocked",
                error=str(exc),
            )
        except PublisherError as exc:
            return PublishResultItem(
                skill_id=item.skill_id, target=item.target, status="error",
                error=str(exc),
            )

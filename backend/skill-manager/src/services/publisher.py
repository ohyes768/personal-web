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

GitHub 条目直接软链到仓库缓存的登记目录；单项根 Skill 使用仓库根目录。
仓库更新会直接影响同仓库的所有已安装成员，不维护逐 Skill 版本快照。
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import uuid
from src.services.operation_lock import serialized

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
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
# 仅用于删除旧版本遗留的 staging 目录，不再生成快照。
_STAGING_PARENT = "staging"


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

    仅服务 local 条目；GitHub 经 resolve_github_source 解析仓库缓存目录。
    """
    if skill.source is not SkillSource.LOCAL:
        raise InvalidSourceError(
            f"github skill {skill.id!r} resolves via repository cache, not local source"
        )
    candidate = (settings.skills_source_root / skill.path).resolve()
    return validated_source(settings, candidate)


def resolve_github_source(settings: Settings, skill: RegistrySkill, repo_dir: Path) -> Path:
    """只读解析仓库根或登记子目录；不生成快照、不拷贝 shared_paths。"""
    repo = repo_dir.resolve()
    if not repo.is_relative_to(settings.github_skill_cache_root):
        raise InvalidSourceError(f"repository cache {repo_dir} is outside the GitHub cache root")
    path = PurePosixPath(skill.path)
    if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
        raise InvalidSourceError(f"invalid repository skill path: {skill.path!r}")
    source = (repo / skill.path).resolve()
    if not source.is_relative_to(repo):
        raise InvalidSourceError(f"skill path {skill.path!r} escapes the repository root")
    return validated_source(settings, source)


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

    # ---------- 旧快照的兼容清理（不再生成新快照） ----------

    def remove_staging(self, skill_id: str) -> None:
        """删除某 skill 的全部 staging rev 目录（删除登记时清理，尽力而为）。"""
        skill_staging = self.settings.github_skill_cache_root / _STAGING_PARENT / skill_id
        if skill_staging.is_dir():
            shutil.rmtree(skill_staging, onexc=_force_remove_tree)

    # ---------- 发布 ----------

    @serialized
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

    @serialized
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

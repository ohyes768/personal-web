"""存量布局迁移与 active 部署自动重发布（2026-09-30 批量登记任务）。

共享缓存模型上线时的一次性兼容逻辑，lifespan 启动时执行：

1. `migrate_legacy_cache`：旧「每 skill.id 一份整仓 clone」布局
   （`${GITHUB_SKILL_CACHE_ROOT}/<skill.id>/`）搬到新仓库维度布局
   （`${GITHUB_SKILL_CACHE_ROOT}/repos/<owner>__<repo>/`）。同仓库多份
   旧缓存只保留其一（发布时按各条目记录 revision 重新 fetch/checkout，
   无数据损失），多余副本直接删除。
2. `republish_active_github_skills`：迁移后原 symlink target（旧缓存
   子目录路径）失效，对 deployment 记录中 status=active 的 github 条目
   自动重组 staging 并替换链接——等价自动重发布，让账实重新一致。

两者都**不依赖网络**（绝不 fetch/clone）：重发布用缓存当前 checkout
状态组装 staging；缓存缺失的条目记 history error 交由 UI 的
link_missing 暴露，不阻断启动。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from src.config import Settings
from src.db import HistoryEntry, SkillStateStore
from src.models import LINK_TARGET_IDS, RegistrySkill, SkillSource, TargetKey
from src.services.git_cache import GitCacheService
from src.services.publisher import (
    Publisher,
    PublisherError,
    force_remove_tree,
)
from src.services.registry import RegistryService

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def migrate_legacy_cache(
    settings: Settings, skills: list[RegistrySkill]
) -> tuple[int, int]:
    """旧 `<cache>/<skill.id>/` 缓存搬移到 `repos/<owner>__<repo>/`。

    返回 (搬移数, 丢弃的多余副本数)；单项失败只记日志，绝不阻断启动。
    """
    moved = 0
    discarded = 0
    seen_repos: set[Path] = set()
    for skill in skills:
        if skill.source is not SkillSource.GITHUB or skill.repository is None:
            continue
        legacy = settings.github_skill_cache_root / skill.id
        if not (legacy / ".git").is_dir():
            continue
        target = _repo_dir_for(settings, skill)
        if target in seen_repos or (target / ".git").is_dir():
            # 同仓库多份旧缓存：保留先落地的一份，其余删除（发布时
            # 会按各条目记录 revision 重新 fetch/checkout）
            try:
                force_remove_tree(legacy)
                discarded += 1
            except OSError as exc:
                logger.warning(
                    "legacy cache discard failed: skill=%s error=%s",
                    skill.id,
                    exc,
                )
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            legacy.replace(target)
            seen_repos.add(target)
            moved += 1
            logger.info("legacy cache moved: skill=%s -> %s", skill.id, target)
        except OSError as exc:
            logger.warning(
                "legacy cache move failed: skill=%s error=%s", skill.id, exc
            )
    return moved, discarded


def republish_active_github_skills(
    settings: Settings,
    registry: RegistryService,
    store: SkillStateStore,
    publisher: Publisher,
    git_cache: GitCacheService,
) -> int:
    """对 active 的 github 部署重组 staging 并替换 symlink（无网络）。

    返回成功重发布的数量；失败逐条记 deployment_history（result=error）
    与 warning 日志，不阻断启动——缓存缺失的条目由 UI 的 link_missing
    暴露，管理员经 Clone 重建后再手动发布。
    """
    republished = 0
    for record in store.list_deployments():
        if record.status != "active":
            continue
        if record.target not in LINK_TARGET_IDS:
            continue
        target = TargetKey(record.target)
        skill = registry.get(record.skill_id)
        if skill is None or skill.source is not SkillSource.GITHUB:
            continue
        try:
            repo_dir = _repo_dir_for(settings, skill)
            if not (repo_dir / ".git").is_dir():
                raise PublisherError(
                    f"repository cache for {skill.repository} does not exist"
                )
            revision = git_cache.current_revision(skill)
            source = publisher.stage_github_skill(skill, revision, repo_dir)
            publisher.publish(skill.id, target, source, revision)
        except PublisherError as exc:
            store.append_history(
                HistoryEntry(
                    skill_id=skill.id,
                    target=target.value,
                    action="publish",
                    result="error",
                    previous_link_target=None,
                    new_link_target=None,
                    source_revision=record.source_revision,
                    error=f"启动迁移重发布失败：{exc}",
                    created_at=_utc_now_iso(),
                )
            )
            logger.warning(
                "startup republish failed: skill=%s target=%s error=%s",
                skill.id,
                target.value,
                exc,
            )
            continue
        republished += 1
    return republished


def _repo_dir_for(settings: Settings, skill: RegistrySkill) -> Path:
    """从 registry 条目直接派生仓库缓存目录（不经过 git_cache 实例方法，
    迁移阶段 git_cache 可能尚未构造；URL 已在登记时规范化）。"""
    from src.services.git_cache import _GITHUB_HTTPS_RE  # 延迟导入避免环

    match = _GITHUB_HTTPS_RE.match(str(skill.repository))
    if match is None:
        raise PublisherError(
            f"skill {skill.id!r} has invalid repository {skill.repository}"
        )
    return (
        settings.github_skill_cache_root
        / "repos"
        / f"{match['owner']}__{match['repo']}"
    )

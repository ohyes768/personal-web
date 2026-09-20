"""HTTP 路由边界（design 7）：公开只读端点 + 密码保护的写端点。

- 公开：列表、GitHub 扫描、更新检查、发布计划（计划绝不改文件系统）；
- 密码（R5）：登记 GitHub Skill、发布、回滚、下架；
- 错误契约统一 `{"code": "...", "message": 中文, 可选 "item_id"}`：
  非法 id/path/target → 400；冲突 → 409；未知 skill → 404；
  批量发布以 200 + 逐项 status/code 表达部分成功（单项失败不回滚他项）；
- 服务端从注册表解析全部文件系统路径，调用方只能传 id 与 target 枚举。
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import (
    ensure_admin_password,
    get_git_cache,
    get_publisher,
    get_registry,
    get_settings,
    get_store,
)
from src.config import Settings
from src.db import GithubCheckRecord, SkillStateStore
from src.models import (
    AdminPasswordRequest,
    CheckUpdatesRequest,
    PlanItem,
    PlanResponse,
    PublishBatchResult,
    PublishPlanRequest,
    PublishRequest,
    PublishResultItem,
    RegisterGithubSkillRequest,
    RegistrySkill,
    ScanRequest,
    ScanResponse,
    SkillCard,
    SkillId,
    SkillListResponse,
    SkillSource,
    SKILL_ID_PATTERN,
    TargetDeployment,
    TargetKey,
    UnpublishResponse,
    UpdateCheckItem,
    UpdateCheckResponse,
    UpdateInfo,
)
from src.services.git_cache import GitCacheError, GitCacheService
from src.services.publisher import (
    InvalidSourceError,
    PublishBlockedError,
    Publisher,
    PublisherError,
    RollbackUnavailableError,
    resolve_registry_source,
)
from src.services.registry import RegistryService, RegistryValidationError

router = APIRouter(prefix="/api")

_ID_RE = re.compile(SKILL_ID_PATTERN)


# ---------- 公开：Skill 列表 ----------


@router.get("/skills", response_model=SkillListResponse)
def list_skills(
    registry: RegistryService = Depends(get_registry),
    store: SkillStateStore = Depends(get_store),
) -> SkillListResponse:
    """左栏卡片：注册表 + 部署状态 + 最近一次更新检查。"""
    try:
        skills = registry.load().skills
    except RegistryValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "registry_invalid", "message": f"注册表加载失败：{exc}"},
        ) from exc
    deployments: dict[str, dict[str, TargetDeployment]] = {}
    for record in store.list_deployments():
        deployments.setdefault(record.skill_id, {})[record.target] = TargetDeployment(
            status=record.status,
            revision=record.source_revision,
            published_at=record.published_at,
            link_target=record.current_link_target,
        )
    cards = [
        _build_card(skill, deployments.get(skill.id, {}), store.get_github_check(skill.id))
        for skill in skills
    ]
    return SkillListResponse(items=cards)


def _build_card(
    skill: RegistrySkill,
    deployments: dict[str, TargetDeployment],
    check: GithubCheckRecord | None,
) -> SkillCard:
    update: UpdateInfo | None = None
    if check is not None and check.result == "ok":
        update = UpdateInfo(
            skill_id=check.skill_id,
            repository=check.repository,
            remote_revision=check.remote_revision,
            remote_tags=[tag for tag in check.remote_tags.split(",") if tag],
            cached_revision=check.cached_revision,
            has_update=check.remote_revision != check.cached_revision,
            checked_at=check.checked_at,
        )
    return SkillCard(
        id=skill.id,
        name=skill.name,
        source=skill.source,
        path=skill.path,
        repository=str(skill.repository) if skill.repository else None,
        tags=skill.tags,
        summary=skill.summary,
        status=skill.status,
        deployments=deployments,
        update=update,
    )


# ---------- 公开：GitHub 扫描 ----------


@router.post("/skills/github/scan", response_model=ScanResponse)
def scan_github_repository(
    req: ScanRequest,
    git_cache: GitCacheService = Depends(get_git_cache),
) -> ScanResponse:
    """临时 clone 扫描候选 `SKILL.md` 目录；失败以 400 表达非法仓库。"""
    try:
        canonical = git_cache.normalize_repository(req.repository)
        candidates = git_cache.scan(req.repository)
    except GitCacheError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_repository", "message": f"仓库地址无效或不可访问：{exc}"},
        ) from exc
    return ScanResponse(repository=canonical, candidates=candidates)


# ---------- 密码：登记 GitHub Skill ----------


@router.post("/skills/github", response_model=SkillCard)
def register_github_skill(
    req: RegisterGithubSkillRequest,
    settings: Settings = Depends(get_settings),
    registry: RegistryService = Depends(get_registry),
    git_cache: GitCacheService = Depends(get_git_cache),
    store: SkillStateStore = Depends(get_store),
) -> SkillCard:
    """登记候选目录：缓存落地 → 注册表 upsert → 返回新卡片（design 5）。

    skill id 由服务端从仓库与路径派生；重复 repository+path → 409。
    """
    ensure_admin_password(settings, req.password)
    try:
        canonical = git_cache.normalize_repository(req.repository)
    except GitCacheError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_repository", "message": f"仓库地址无效：{exc}"},
        ) from exc
    skill_id = _derive_skill_id(registry, canonical, req.path)
    skill = RegistrySkill(
        id=skill_id,
        name=req.name,
        source=SkillSource.GITHUB,
        path=req.path,
        repository=canonical,
        tags=req.tags,
        summary=req.summary,
    )
    try:
        info = git_cache.check_update(skill)
        git_cache.ensure_cached(skill, info.remote_revision)
    except GitCacheError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "cache_failed", "message": f"GitHub 仓库缓存失败：{exc}"},
        ) from exc
    try:
        registry.upsert(skill)
    except RegistryValidationError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "registry_conflict", "message": f"注册表写入被拒绝：{exc}"},
        ) from exc
    _commit_registry_best_effort(registry)
    return _build_card(skill, {}, store.get_github_check(skill.id))


def _derive_skill_id(registry: RegistryService, canonical: str, path: str) -> str:
    """从仓库与路径派生稳定 slug；与现有条目冲突时追加序号。"""
    existing = {s.id for s in registry.load().skills}
    repo_name = canonical.rstrip("/").rsplit("/", 1)[-1]
    parts = [repo_name]
    if path not in (".", ""):
        parts.append(re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-").split("-")[-1])
    slug = re.sub(r"[^a-z0-9]+", "-", "-".join(parts).lower()).strip("-")
    if not slug:
        slug = "skill"
    slug = slug[:63].rstrip("-") or "skill"
    if not _ID_RE.match(slug):
        slug = f"skill-{slug}"[:63].rstrip("-")
    candidate = slug
    counter = 2
    while candidate in existing:
        candidate = f"{slug}-{counter}"
        counter += 1
    return candidate


def _commit_registry_best_effort(registry: RegistryService) -> None:
    """注册表 Git 提交尽力而为：非 Git 环境/提交失败不阻断登记。"""
    try:
        registry.commit_registry_change()
    except Exception:
        # 测试源库与部分 NAS 源库可能没有 Git 历史；登记本身已落盘
        pass


# ---------- 公开：更新检查 ----------


@router.post("/skills/check-updates", response_model=UpdateCheckResponse)
def check_updates(
    req: CheckUpdatesRequest,
    registry: RegistryService = Depends(get_registry),
    git_cache: GitCacheService = Depends(get_git_cache),
) -> UpdateCheckResponse:
    """只读检查远端/缓存版本差异；绝不 fetch 缓存、绝不发布（R3）。"""
    skills = registry.load().skills
    selected = [
        skill
        for skill in skills
        if skill.source is SkillSource.GITHUB
        and (not req.skill_ids or skill.id in req.skill_ids)
    ]
    reported = {skill.id for skill in selected}
    items: list[UpdateCheckItem] = [
        UpdateCheckItem(skill_id=skill_id, result="error", error="未知 skill，或该 skill 不是 GitHub 来源")
        for skill_id in req.skill_ids
        if skill_id not in reported
    ]
    for skill in selected:
        try:
            items.append(
                UpdateCheckItem(
                    skill_id=skill.id, result="ok", info=git_cache.check_update(skill)
                )
            )
        except GitCacheError as exc:
            items.append(
                UpdateCheckItem(skill_id=skill.id, result="error", error=str(exc))
            )
    return UpdateCheckResponse(items=items)


# ---------- 公开：发布计划 ----------


@router.post("/skills/publish/plan", response_model=PlanResponse)
def publish_plan(
    req: PublishPlanRequest,
    settings: Settings = Depends(get_settings),
    registry: RegistryService = Depends(get_registry),
    store: SkillStateStore = Depends(get_store),
    git_cache: GitCacheService = Depends(get_git_cache),
) -> PlanResponse:
    """右栏计划预览：逐项 add/update/unchanged/blocked；只读（design 4.2）。"""
    known = {skill.id: skill for skill in registry.load().skills}
    items: list[PlanItem] = []
    for queue_item in req.items:
        skill = known.get(queue_item.skill_id)
        if skill is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "skill_not_found",
                    "message": f"未知 skill：{queue_item.skill_id}",
                    "item_id": queue_item.skill_id,
                },
            )
        for target in queue_item.targets:
            items.append(_plan_one(settings, store, git_cache, skill, target))
    return PlanResponse(items=items)


def _plan_one(
    settings: Settings,
    store: SkillStateStore,
    git_cache: GitCacheService,
    skill: RegistrySkill,
    target: TargetKey,
) -> PlanItem:
    """单项计划：解析受控源 + 检查目标现状，绝不写入文件系统。"""
    try:
        source = resolve_registry_source(settings, skill)
    except InvalidSourceError as exc:
        return PlanItem(
            skill_id=skill.id, target=target, action="blocked",
            reason=f"源不可用：{exc}",
        )
    final_link = _target_root(settings, target) / skill.id
    if final_link.is_symlink():
        resolved_link = final_link.resolve()
        if not _inside_controlled_roots(settings, resolved_link):
            return PlanItem(
                skill_id=skill.id, target=target, action="blocked",
                reason=f"现有链接指向受控目录之外：{resolved_link}",
            )
        action = "unchanged" if resolved_link == source else "update"
    elif final_link.exists():
        return PlanItem(
            skill_id=skill.id, target=target, action="blocked",
            reason="目标位置已被普通目录或文件占用",
        )
    else:
        action = "add"
    deployment = store.get_deployment(skill.id, target.value)
    planned_revision = _planned_revision(store, git_cache, skill)
    return PlanItem(
        skill_id=skill.id,
        target=target,
        action=action,
        current_revision=deployment.source_revision if deployment else "",
        planned_revision=planned_revision,
    )


def _planned_revision(
    store: SkillStateStore, git_cache: GitCacheService, skill: RegistrySkill
) -> str:
    """GitHub 条目以最近一次成功检查的远端 revision 为准（发布将检出它）；
    无记录时退回缓存 HEAD。全程只读，绝不 fetch（design 4.2/5）。"""
    if skill.source is not SkillSource.GITHUB:
        return ""
    check = store.get_github_check(skill.id)
    if check is not None and check.result == "ok" and check.remote_revision:
        return check.remote_revision
    return git_cache.current_revision(skill.id)


def _target_root(settings: Settings, target: TargetKey) -> Path:
    roots = {
        TargetKey.OPENCLAW: settings.openclaw_skills_root,
        TargetKey.HERMES: settings.hermes_skills_root,
    }
    return roots[target]


def _inside_controlled_roots(settings: Settings, resolved: Path) -> bool:
    return resolved.is_relative_to(
        settings.skills_source_root
    ) or resolved.is_relative_to(settings.github_skill_cache_root)


# ---------- 密码：执行发布 ----------


@router.post("/skills/publish", response_model=PublishBatchResult)
def publish(
    req: PublishRequest,
    settings: Settings = Depends(get_settings),
    registry: RegistryService = Depends(get_registry),
    publisher: Publisher = Depends(get_publisher),
    git_cache: GitCacheService = Depends(get_git_cache),
    store: SkillStateStore = Depends(get_store),
) -> PublishBatchResult:
    """执行发布：逐项独立事务，单项失败只记录该项（design 6.1 / 7）。"""
    ensure_admin_password(settings, req.password)
    known = {skill.id: skill for skill in registry.load().skills}
    results: list[PublishResultItem] = []
    for queue_item in req.items:
        skill = known.get(queue_item.skill_id)
        if skill is None:
            results.extend(
                PublishResultItem(
                    skill_id=queue_item.skill_id,
                    target=target,
                    status="error",
                    error=f"未知 skill：{queue_item.skill_id}",
                )
                for target in queue_item.targets
            )
            continue
        for target in queue_item.targets:
            results.append(
                _publish_one(settings, publisher, git_cache, store, skill, target)
            )
    return PublishBatchResult(items=results)


def _publish_one(
    settings: Settings,
    publisher: Publisher,
    git_cache: GitCacheService,
    store: SkillStateStore,
    skill: RegistrySkill,
    target: TargetKey,
) -> PublishResultItem:
    try:
        if skill.source is SkillSource.GITHUB:
            # design 5 / R3：实际缓存更新仅随管理员确认的发布执行——
            # 发布时才 fetch 并检出最近一次成功检查记录的远端 revision
            _ensure_cached_at_recorded_revision(git_cache, store, skill)
        source = resolve_registry_source(settings, skill)
    except GitCacheError as exc:
        return PublishResultItem(
            skill_id=skill.id, target=target, status="error",
            error=f"GitHub 缓存更新失败：{exc}",
        )
    except InvalidSourceError as exc:
        return PublishResultItem(
            skill_id=skill.id, target=target, status="blocked",
            error=f"源不可用：{exc}",
        )
    revision = (
        git_cache.current_revision(skill.id)
        if skill.source is SkillSource.GITHUB
        else ""
    )
    try:
        return publisher.publish(skill.id, target, source, revision)
    except PublishBlockedError as exc:
        return PublishResultItem(
            skill_id=skill.id, target=target, status="blocked", error=str(exc)
        )
    except PublisherError as exc:
        return PublishResultItem(
            skill_id=skill.id, target=target, status="error", error=str(exc)
        )


def _ensure_cached_at_recorded_revision(
    git_cache: GitCacheService, store: SkillStateStore, skill: RegistrySkill
) -> None:
    """把 GitHub 缓存更新到最近一次成功检查记录的远端 revision。

    无成功检查记录时保持缓存现状（登记后从未检查过的场景，缓存即登记版本）。
    """
    check = store.get_github_check(skill.id)
    if check is not None and check.result == "ok" and check.remote_revision:
        git_cache.ensure_cached(skill, check.remote_revision)


# ---------- 密码：回滚与下架 ----------


@router.post(
    "/skills/{skill_id}/targets/{target}/rollback",
    response_model=PublishResultItem,
)
def rollback(
    skill_id: str,
    target: str,
    req: AdminPasswordRequest,
    settings: Settings = Depends(get_settings),
    registry: RegistryService = Depends(get_registry),
    publisher: Publisher = Depends(get_publisher),
) -> PublishResultItem:
    """回滚到该 target 最近一次成功快照；无快照 → 409（design 6.2）。"""
    ensure_admin_password(settings, req.password)
    _require_known_skill(registry, _require_skill_id(skill_id))
    target_key = _require_target(target)
    try:
        return publisher.rollback(skill_id, target_key)
    except RollbackUnavailableError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "rollback_unavailable",
                "message": f"没有可回滚的快照：{exc}",
                "item_id": skill_id,
            },
        ) from exc
    except InvalidSourceError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_source", "message": f"快照目标不可用：{exc}", "item_id": skill_id},
        ) from exc
    except PublishBlockedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "target_blocked", "message": f"目标被阻止：{exc}", "item_id": skill_id},
        ) from exc
    except PublisherError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "rollback_failed", "message": f"回滚失败：{exc}", "item_id": skill_id},
        ) from exc


@router.delete(
    "/skills/{skill_id}/targets/{target}",
    response_model=UnpublishResponse,
)
def unpublish(
    skill_id: str,
    target: str,
    req: AdminPasswordRequest,
    settings: Settings = Depends(get_settings),
    registry: RegistryService = Depends(get_registry),
    publisher: Publisher = Depends(get_publisher),
) -> UnpublishResponse:
    """下架：仅删除受管 symlink 本身，绝不递归删除目录（design 6.2）。

    密码经请求体 `{password}` 传输，与全部写操作契约一致（避免 header
    编码与代理日志差异）；下架与“移出发布队列”无关。
    """
    ensure_admin_password(settings, req.password)
    _require_known_skill(registry, _require_skill_id(skill_id))
    target_key = _require_target(target)
    try:
        publisher.unpublish(skill_id, target_key)
    except PublishBlockedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "target_blocked", "message": f"下架被拒绝：{exc}", "item_id": skill_id},
        ) from exc
    except PublisherError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "unpublish_failed", "message": f"下架失败：{exc}", "item_id": skill_id},
        ) from exc
    return UnpublishResponse(skill_id=skill_id, target=target_key)


# ---------- 参数校验 helper ----------


def _require_skill_id(skill_id: str) -> str:
    if not _ID_RE.match(skill_id):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_skill_id",
                "message": f"非法的 skill id：{skill_id!r}",
            },
        )
    return skill_id


def _require_target(target: str) -> TargetKey:
    try:
        return TargetKey(target)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_target",
                "message": f"未知发布目标：{target!r}（只支持 openclaw / hermes）",
            },
        ) from exc


def _require_known_skill(registry: RegistryService, skill_id: str) -> None:
    known = {skill.id for skill in registry.load().skills}
    if skill_id not in known:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "skill_not_found",
                "message": f"未知 skill：{skill_id}",
                "item_id": skill_id,
            },
        )

"""HTTP 路由边界（design 7）：公开只读端点 + 密码保护的写端点。

- 公开：列表、GitHub 扫描、更新检查、发布计划（计划绝不改文件系统）；
- 密码（R5）：登记 GitHub Skill、发布、回滚、下架；
- 错误契约统一 `{"code": "...", "message": 中文, 可选 "item_id"}`：
  非法 id/path/target → 400；冲突 → 409；未知 skill → 404；
  批量发布以 200 + 逐项 status/code 表达部分成功（单项失败不回滚他项）；
- 服务端从注册表解析全部文件系统路径，调用方只能传 id 与 target 枚举。
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
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
    DeleteSkillResponse,
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
    UpdateSkillTagsRequest,
    UpdateSkillTagsResponse,
)
from src.services.git_cache import GitCacheError, GitCacheService
from src.services.publisher import (
    InvalidSourceError,
    PublishBlockedError,
    Publisher,
    PublisherError,
    resolve_registry_source,
)
from src.services.registry import RegistryService, RegistryValidationError

router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)

_ID_RE = re.compile(SKILL_ID_PATTERN)


# ---------- 公开：Skill 列表 ----------


@router.get("/skills", response_model=SkillListResponse)
def list_skills(
    registry: RegistryService = Depends(get_registry),
    store: SkillStateStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> SkillListResponse:
    """左栏卡片：先对账自研目录再返回注册表 + 部署状态 + 更新检查。

    对账失败（源库不可达/登记写库异常）只记日志，列表降级为现有登记，
    绝不因同步问题返回 5xx（PRD R4）。
    """
    try:
        synced = registry.sync_local()
        if synced:
            logger.info("local sync: registered %d new skills", synced)
    except (OSError, RegistryValidationError, sqlite3.Error) as exc:
        logger.warning("local sync failed, falling back to existing registry: %s", exc)
    skills = registry.list_skills()
    deployments: dict[str, dict[str, TargetDeployment]] = {}
    for record in store.list_deployments():
        # 账实核对：active 记录对目标链接做 lstat 存在性检查（纯 lstat，
        # 每条一次，零子进程）；removed 记录不出徽章，不检查
        link_missing = record.status == "active" and not (
            _target_root(settings, TargetKey(record.target)) / record.skill_id
        ).is_symlink()
        deployments.setdefault(record.skill_id, {})[record.target] = TargetDeployment(
            status=record.status,
            revision=record.source_revision,
            published_at=record.published_at,
            link_target=record.current_link_target,
            link_missing=link_missing,
        )
    cards = [
        _build_card(
            settings,
            skill,
            deployments.get(skill.id, {}),
            store.get_github_check(skill.id),
            # 与 ensure_cached 决定 fetch/clone 的口径一致：纯文件系统判断，
            # 零 git 子进程；注册表随源库同步而缓存环境本地，缺失属常态
            cache_missing=skill.source is SkillSource.GITHUB
            and not (settings.github_skill_cache_root / skill.id / ".git").is_dir(),
        )
        for skill in skills
    ]
    return SkillListResponse(items=cards)


def _build_card(
    settings: Settings,
    skill: RegistrySkill,
    deployments: dict[str, TargetDeployment],
    check: GithubCheckRecord | None,
    cache_missing: bool = False,
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
    source_missing = (
        skill.source is SkillSource.LOCAL
        and not (settings.skills_source_root / skill.path / "SKILL.md").is_file()
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
        cache_missing=cache_missing,
        source_missing=source_missing,
    )


# ---------- 公开：GitHub 扫描 ----------


@router.post("/skills/github/scan", response_model=ScanResponse)
def scan_github_repository(
    req: ScanRequest,
    git_cache: GitCacheService = Depends(get_git_cache),
) -> ScanResponse:
    """临时 clone 扫描候选 `SKILL.md` 目录；失败以 400 表达非法仓库。"""
    canonical = ""
    try:
        canonical = git_cache.normalize_repository(req.repository)
        logger.info("scan github start: repository=%s", canonical)
        candidates = git_cache.scan(canonical)
    except GitCacheError as exc:
        logger.warning(
            "scan github failed: repository=%s error_type=%s",
            canonical or "<invalid>",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_repository", "message": f"仓库地址无效或不可访问：{exc}"},
        ) from exc
    logger.info("scan github done: repository=%s candidates=%d", canonical, len(candidates))
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
        logger.warning(
            "register github invalid repository: error=%s", type(exc).__name__
        )
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
    logger.info(
        "register github start: skill=%s repository=%s path=%r",
        skill_id, canonical, req.path,
    )
    stage = "remote_check"
    try:
        info = git_cache.check_update(skill)
        logger.info(
            "register github remote checked: skill=%s revision=%s",
            skill_id, info.remote_revision,
        )
        stage = "cache_checkout"
        git_cache.ensure_cached(skill, info.remote_revision)
        logger.info(
            "register github cache ready: skill=%s revision=%s",
            skill_id, info.remote_revision,
        )
    except GitCacheError as exc:
        logger.warning(
            "register github failed: skill=%s stage=%s error_type=%s",
            skill_id, stage, type(exc).__name__,
        )
        raise HTTPException(
            status_code=400,
            detail={"code": "cache_failed", "message": f"GitHub 仓库缓存失败：{exc}"},
        ) from exc
    try:
        registry.upsert(skill)
    except RegistryValidationError as exc:
        logger.warning(
            "register github failed: skill=%s stage=registry error_type=%s",
            skill_id, type(exc).__name__,
        )
        raise HTTPException(
            status_code=409,
            detail={"code": "registry_conflict", "message": f"注册表写入被拒绝：{exc}"},
        ) from exc
    logger.info("register github done: skill=%s", skill_id)
    return _build_card(settings, skill, {}, store.get_github_check(skill.id))


def _derive_skill_id(registry: RegistryService, canonical: str, path: str) -> str:
    """从仓库与路径派生稳定 slug；与现有条目冲突时追加序号。"""
    existing = {s.id for s in registry.list_skills()}
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


# ---------- 密码：重建 GitHub 缓存（Clone） ----------


@router.post("/skills/github/{skill_id}/clone")
def clone_github_cache(
    skill_id: str,
    req: AdminPasswordRequest,
    settings: Settings = Depends(get_settings),
    registry: RegistryService = Depends(get_registry),
    git_cache: GitCacheService = Depends(get_git_cache),
) -> dict[str, str]:
    """重建本环境缺失的 GitHub 缓存，返回检出的 revision。

    语义与登记流程一致（design 5）：`check_update()` 只读 ls-remote 并刷新
    检查记录 → `ensure_cached()` clone/fetch 并检出远端 revision。刻意不走
    `_ensure_cached_at_recorded_revision`——它在无成功检查记录时是 no-op，
    对"缓存根本不存在"的场景无效。只写 GITHUB_SKILL_CACHE_ROOT 之内，
    不触碰源库与目标目录。
    """
    ensure_admin_password(settings, req.password)
    skill = _require_known_skill(registry, _require_skill_id(skill_id))
    if skill.source is not SkillSource.GITHUB:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_skill",
                "message": f"skill {skill.id} 不是 GitHub 来源，无需 Clone 缓存",
                "item_id": skill.id,
            },
        )
    # clone 大仓库可能持续数分钟，主动打日志避免"请求期间无任何输出"
    logger.info("clone cache start: skill=%s repository=%s", skill.id, skill.repository)
    stage = "remote_check"
    try:
        info = git_cache.check_update(skill)
        logger.info(
            "clone cache remote checked: skill=%s revision=%s", skill.id, info.remote_revision
        )
        stage = "cache_checkout"
        git_cache.ensure_cached(skill, info.remote_revision)
    except GitCacheError as exc:
        logger.warning(
            "clone cache failed: skill=%s stage=%s error_type=%s",
            skill.id, stage, type(exc).__name__,
        )
        raise HTTPException(
            status_code=400,
            detail={"code": "cache_failed", "message": f"GitHub 缓存更新失败：{exc}"},
        ) from exc
    logger.info(
        "clone cache done: skill=%s revision=%s", skill.id, info.remote_revision
    )
    return {"skill_id": skill.id, "revision": info.remote_revision}


# ---------- 公开：更新检查 ----------


@router.post("/skills/check-updates", response_model=UpdateCheckResponse)
def check_updates(
    req: CheckUpdatesRequest,
    registry: RegistryService = Depends(get_registry),
    git_cache: GitCacheService = Depends(get_git_cache),
) -> UpdateCheckResponse:
    """只读检查远端/缓存版本差异；绝不 fetch 缓存、绝不发布（R3）。"""
    skills = registry.list_skills()
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
    known = {skill.id: skill for skill in registry.list_skills()}
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
    known = {skill.id: skill for skill in registry.list_skills()}
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


# ---------- 密码：下架 ----------


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


@router.delete("/skills/{skill_id}", response_model=DeleteSkillResponse)
def delete_skill(
    skill_id: str,
    req: AdminPasswordRequest,
    settings: Settings = Depends(get_settings),
    registry: RegistryService = Depends(get_registry),
    store: SkillStateStore = Depends(get_store),
) -> DeleteSkillResponse:
    """删除已登记的 Skill（design：任一 target active 时拒绝）。

    - GitHub 来源：删除登记 + 清理本地缓存；
    - 本地来源：仅删除数据库登记记录（源目录若存在则拒绝，移除目录后自动解除）。

    登记真源是 SQLite：先移除 DB 行，派生数据随后尽力清理。"""
    ensure_admin_password(settings, req.password)
    _require_skill_id(skill_id)
    skill = _require_known_skill(registry, skill_id, code="unknown_skill")
    if skill.source is SkillSource.LOCAL:
        source_dir = settings.skills_source_root / skill.path
        if source_dir.exists():
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "local_source",
                    "message": f"skill {skill.id} 是本地来源，不支持删除（移除源目录即消失）",
                    "item_id": skill.id,
                },
            )
        # 源目录不存在，允许删除数据库登记记录
    active = [
        record
        for record in store.list_deployments()
        if record.skill_id == skill_id and record.status == "active"
    ]
    if active:
        targets = ", ".join(record.target for record in active)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "skill_active",
                "message": f"skill {skill_id} 仍有 active 部署（{targets}），请先下架",
                "item_id": skill_id,
            },
        )
    try:
        registry.remove(skill_id)
    except RegistryValidationError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_skill",
                "message": f"未知 skill：{skill_id}",
                "item_id": skill_id,
            },
        ) from exc
    try:
        store.delete_github_check(skill_id)
    except sqlite3.Error as exc:
        # design：派生数据尽力清理，失败不改变响应（registry 真源已提交）
        logger.warning("delete derived state failed: skill=%s error=%s", skill_id, exc)
    try:
        shutil.rmtree(settings.github_skill_cache_root / skill_id)
    except OSError as exc:
        logger.warning("delete cache failed: skill=%s error=%s", skill_id, exc)
    return DeleteSkillResponse(skill_id=skill_id)


# ---------- 编辑标签 ----------


@router.patch("/skills/{skill_id}/tags", response_model=UpdateSkillTagsResponse)
def update_skill_tags(
    skill_id: str,
    req: UpdateSkillTagsRequest,
    registry: RegistryService = Depends(get_registry),
) -> UpdateSkillTagsResponse:
    """单卡标签全量替换：排序去重后落库，返回替换结果。

    源目录缺失的 local 条目同样可编辑（标签维护不依赖源存在），
    故走 `update_skill_tags` 而非完整 `upsert()` 校验。
    """
    _require_skill_id(skill_id)
    try:
        updated = registry.update_skill_tags(skill_id, req.tags)
    except RegistryValidationError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_skill",
                "message": f"未知 skill：{skill_id}",
                "item_id": skill_id,
            },
        ) from exc
    return UpdateSkillTagsResponse(skill_id=updated.id, tags=updated.tags)


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


def _require_known_skill(
    registry: RegistryService, skill_id: str, code: str = "skill_not_found"
) -> RegistrySkill:
    skill = registry.get(skill_id)
    if skill is not None:
        return skill
    raise HTTPException(
        status_code=404,
        detail={
            "code": code,
            "message": f"未知 skill：{skill_id}",
            "item_id": skill_id,
        },
    )

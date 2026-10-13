"""Whole-repository management; credentials stop at this HTTP boundary."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from src.api.dependencies import (
    ensure_admin_password, get_settings, get_store, get_git_cache, get_task_manager,
)
from src.config import Settings
from src.db import SkillStateStore
from src.models import (
    PackAddRequest, PackTargetsRequest, PackInstallRequest, PackAdminRequest,
    GithubPack, PackPlan, TaskSnapshot, AsyncTaskCreatedResponse, SkillId,
)
from src.services.git_cache import GitCacheService
from src.services.packs import PackService, PackError
from src.services.task_manager import GithubTaskManager

router = APIRouter(prefix="/api/github-packs")


def get_packs(
    request: Request,
    settings: Settings = Depends(get_settings),
    store: SkillStateStore = Depends(get_store),
    git_cache: GitCacheService = Depends(get_git_cache),
) -> PackService:
    # Honor dependency overrides for offline remotes in integration tests.
    service = getattr(request.app.state, "packs", None)
    if service is None or service.git_cache is not git_cache:
        service = PackService(settings, store, git_cache)
    service.migrate_legacy()
    return service


def _http_error(error: PackError) -> HTTPException:
    return HTTPException(error.status, {"code": error.code, "message": error.message})


@router.get("")
def list_packs(service: PackService = Depends(get_packs)) -> dict:
    return {"items": service.list()}


@router.post("", response_model=AsyncTaskCreatedResponse, status_code=202)
def add_pack(
    req: PackAddRequest,
    settings: Settings = Depends(get_settings),
    service: PackService = Depends(get_packs),
    tasks: GithubTaskManager = Depends(get_task_manager),
) -> AsyncTaskCreatedResponse:
    ensure_admin_password(settings, req.password)
    try:
        repository = service._canonical(req.repository)
    except PackError as exc:
        raise _http_error(exc) from exc
    # Copy only public input fields. The closure never retains req/password.
    name, tags, summary = req.name, list(req.tags), req.summary
    task = tasks.start_operation("prepare_pack", repository,
        lambda progress: {"pack": service.add(repository, name, tags, summary,
                                              on_progress=progress).model_dump(mode="json")})
    return AsyncTaskCreatedResponse(task_id=task.task_id, kind=task.kind)


@router.get("/tasks/{task_id}", response_model=TaskSnapshot)
def pack_task(task_id: str, tasks: GithubTaskManager = Depends(get_task_manager)) -> TaskSnapshot:
    task = tasks.get(task_id)
    if task is None or task.kind not in ("prepare_pack", "update_pack", "install_pack"):
        raise HTTPException(404, {"code": "task_not_found",
                                 "message": "任务不存在或已回收，服务重启会丢失进行中的任务"})
    return TaskSnapshot.model_validate(task, from_attributes=True)


@router.get("/{pack_id}", response_model=GithubPack)
def pack_details(pack_id: SkillId, service: PackService = Depends(get_packs)) -> GithubPack:
    try:
        return service.get(pack_id)
    except PackError as exc:
        raise _http_error(exc) from exc


@router.post("/{pack_id}/check-update", response_model=GithubPack)
def check_pack(pack_id: SkillId, service: PackService = Depends(get_packs)) -> GithubPack:
    try:
        return service.check_update(pack_id)
    except PackError as exc:
        raise _http_error(exc) from exc


@router.post("/{pack_id}/update", response_model=AsyncTaskCreatedResponse, status_code=202)
def update_pack(
    pack_id: SkillId, req: PackAdminRequest,
    settings: Settings = Depends(get_settings), service: PackService = Depends(get_packs),
    tasks: GithubTaskManager = Depends(get_task_manager),
) -> AsyncTaskCreatedResponse:
    ensure_admin_password(settings, req.password)
    try:
        pack = service.get(pack_id)
    except PackError as exc:
        raise _http_error(exc) from exc
    task = tasks.start_operation("update_pack", pack.repository,
        lambda progress: {"pack": service.update(pack_id, on_progress=progress).model_dump(mode="json")})
    return AsyncTaskCreatedResponse(task_id=task.task_id, kind=task.kind)


@router.post("/{pack_id}/plan", response_model=PackPlan)
def plan_pack(pack_id: SkillId, req: PackTargetsRequest,
              service: PackService = Depends(get_packs)) -> PackPlan:
    try:
        return service.plan(pack_id, req.targets)
    except PackError as exc:
        raise _http_error(exc) from exc


@router.post("/{pack_id}/install", response_model=AsyncTaskCreatedResponse, status_code=202)
def install_pack(
    pack_id: SkillId, req: PackInstallRequest,
    settings: Settings = Depends(get_settings), service: PackService = Depends(get_packs),
    tasks: GithubTaskManager = Depends(get_task_manager),
) -> AsyncTaskCreatedResponse:
    ensure_admin_password(settings, req.password)
    try:
        pack = service.get(pack_id)
    except PackError as exc:
        raise _http_error(exc) from exc
    targets = list(req.targets)
    task = tasks.start_operation("install_pack", pack.repository,
        lambda progress: service.install(pack_id, targets).model_dump(mode="json"))
    return AsyncTaskCreatedResponse(task_id=task.task_id, kind=task.kind)


@router.delete("/{pack_id}/targets/{target}")
def uninstall_pack(
    pack_id: SkillId, target: str, req: PackAdminRequest,
    settings: Settings = Depends(get_settings), service: PackService = Depends(get_packs),
) -> dict:
    ensure_admin_password(settings, req.password)
    try:
        service.uninstall(pack_id, target)
    except PackError as exc:
        raise _http_error(exc) from exc
    return {"pack_id": pack_id, "target": target, "status": "removed"}


@router.delete("/{pack_id}")
def delete_pack(pack_id: SkillId, req: PackAdminRequest,
                settings: Settings = Depends(get_settings),
                service: PackService = Depends(get_packs)) -> dict:
    ensure_admin_password(settings, req.password)
    try:
        service.delete(pack_id)
    except PackError as exc:
        raise _http_error(exc) from exc
    return {"pack_id": pack_id, "status": "removed"}

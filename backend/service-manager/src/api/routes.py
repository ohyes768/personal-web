"""REST 路由（design §7 表格逐条对应）。

对外路径 `/api/services/*` 由 Nginx 剥成 `/api/*`；本 router 因此挂在
prefix="/api" 下，且认证 cookie Path 也是 `/api/services`（生产）——
开发期前端走 rewrite，同样带前缀。
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse

from src.api.dependencies import (
    get_auth,
    get_checker,
    get_discovery,
    get_jobs,
    get_registry,
    get_resources,
    get_settings,
    get_status_projector,
    get_store,
)
from src.auth import AuthService
from src.backup import (
    BackupError,
    export_payload,
    preview,
    restore,
)
from src.checker import Checker
from src.config import Settings
from src.db import Store
from src.discovery import DiscoveryService
from src.errors import bad_request, not_found, too_large
from src.jobs import JobManager
from src.models import (
    BackupPreviewResponse,
    ComponentOverrideInput,
    DiscoveryCandidate,
    DiscoveryDecisionRequest,
    DiscoveryImportRequest,
    EndpointInput,
    EndpointRecord,
    PrimaryEndpointInput,
    LoginRequest,
    PortNoteInput,
    PortNoteRecord,
    RefreshJobView,
    RefreshRequest,
    ReleaseListResponse,
    ReleaseReadRequest,
    ReleaseSourceInput,
    ReleaseSourceRecord,
    ReleaseView,
    RestoreRequest,
    ServiceCreate,
    ServiceDetail,
    ServiceListItem,
    ServicePatch,
    RefreshKind,
    SessionResponse,
    SummaryResponse,
)
from src.registry import Registry
from src.resources import PORT_SCOPE_NOTE, ResourceProjector
from src.status import StatusProjector

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# 认证依赖
# ---------------------------------------------------------------------------


def require_auth(
    request: Request, auth: Annotated[AuthService, Depends(get_auth)]
) -> None:
    auth.require_session(request)


def require_write(
    request: Request, auth: Annotated[AuthService, Depends(get_auth)]
) -> None:
    auth.require_session(request)
    auth.check_origin(request)


AuthDep = Annotated[None, Depends(require_auth)]
WriteDep = Annotated[None, Depends(require_write)]


# ---------------------------------------------------------------------------
# 健康 / 会话
# ---------------------------------------------------------------------------


@router.get("/health")
def health() -> dict[str, str]:
    """公开最小健康端点：只说明进程 ready，不泄漏台账（design §7）。"""
    return {"status": "ok"}


@router.post("/auth/login", response_model=SessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth)],
) -> SessionResponse:
    client = request.client.host if request.client else "unknown"
    auth.limiter.check(client)
    if not auth.verify_password(payload.password):
        from src.errors import unauthorized

        raise unauthorized("口令不正确")
    auth.limiter.reset(client)
    info = auth.issue(response)
    return SessionResponse(authenticated=True, expires_at=info.expires_at.isoformat(timespec="seconds"))


@router.get("/auth/session", response_model=SessionResponse)
def session_state(
    request: Request, auth: Annotated[AuthService, Depends(get_auth)]
) -> SessionResponse:
    info = auth.read_session(request)
    if info is None:
        return SessionResponse(authenticated=False)
    return SessionResponse(
        authenticated=True, expires_at=info.expires_at.isoformat(timespec="seconds")
    )


@router.post("/auth/logout", response_model=SessionResponse)
def logout(
    response: Response,
    request: Request,
    auth: Annotated[AuthService, Depends(get_auth)],
) -> SessionResponse:
    auth.check_origin(request)
    auth.clear(response)
    return SessionResponse(authenticated=False)


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=SummaryResponse)
def summary(
    _: AuthDep,
    projector: Annotated[StatusProjector, Depends(get_status_projector)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SummaryResponse:
    return SummaryResponse(**projector.summary())


# ---------------------------------------------------------------------------
# 服务台账
# ---------------------------------------------------------------------------


@router.get("/services")
def list_services(
    _: AuthDep,
    registry: Annotated[Registry, Depends(get_registry)],
    projector: Annotated[StatusProjector, Depends(get_status_projector)],
    query: str = Query(default="", max_length=200),
    tag: str = Query(default="", max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    items, total = registry.list_services(
        query=query, tag=tag, page=page, page_size=page_size
    )
    projects = registry.projects_by_service()
    payload = []
    for item in items:
        detail_status = projector.status_for(item.id)
        payload.append(
            item.model_copy(
                update={
                    "status": detail_status,
                    "projects": projects.get(item.id, []),
                }
            ).model_dump()
        )
    return {
        "items": payload,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/services", response_model=ServiceDetail, status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> ServiceDetail:
    detail = registry.create_service(payload)
    return detail


@router.get("/services/{service_id}", response_model=ServiceDetail)
def get_service(
    service_id: str,
    _: AuthDep,
    registry: Annotated[Registry, Depends(get_registry)],
    projector: Annotated[StatusProjector, Depends(get_status_projector)],
) -> ServiceDetail:
    detail = registry.get_service(service_id)
    components = projector.components_for(service_id)
    detail.components = components
    detail.status = projector.status_for(service_id, components=components)
    return detail


@router.patch("/services/{service_id}", response_model=ServiceDetail)
def patch_service(
    service_id: str,
    payload: ServicePatch,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
    projector: Annotated[StatusProjector, Depends(get_status_projector)],
) -> ServiceDetail:
    registry.update_service(service_id, payload)
    detail = registry.get_service(service_id)
    components = projector.components_for(service_id)
    detail.components = components
    detail.status = projector.status_for(service_id, components=components)
    return detail


@router.delete("/services/{service_id}")
def delete_service(
    service_id: str,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> dict[str, Any]:
    return registry.delete_service(service_id)


# ---- 组件绑定 ---------------------------------------------------------------


@router.put("/services/{service_id}/primary-endpoint", response_model=EndpointRecord)
def upsert_primary_endpoint(
    service_id: str,
    payload: PrimaryEndpointInput,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> EndpointRecord:
    """登记/更新主入口：只收 URL，类型与是否查证书由后端按 URL 判定。"""
    return registry.upsert_primary_endpoint(service_id, payload.url)


@router.post("/services/{service_id}/components/{source_key}/required")
def set_component_required(
    service_id: str,
    source_key: str,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
    required: bool = Query(default=True),
    label: str | None = Query(default=None, max_length=120),
) -> dict[str, Any]:
    registry.set_component_required(service_id, source_key, required, label)
    return {"ok": True}


@router.delete("/services/{service_id}/components/{source_key}")
def unbind_component(
    service_id: str,
    source_key: str,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> dict[str, Any]:
    registry.unbind_component(service_id, source_key)
    return {"ok": True}


@router.put("/components/{source_key}/override")
def set_override(
    source_key: str,
    payload: ComponentOverrideInput,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> dict[str, Any]:
    registry.set_override(source_key, payload)
    return {"ok": True}


# ---- 入口 -------------------------------------------------------------------


@router.post(
    "/services/{service_id}/endpoints",
    response_model=EndpointRecord,
    status_code=status.HTTP_201_CREATED,
)
def add_endpoint(
    service_id: str,
    payload: EndpointInput,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> EndpointRecord:
    return registry.add_endpoint(service_id, payload)


@router.put(
    "/services/{service_id}/endpoints/{endpoint_id}",
    response_model=EndpointRecord,
)
def update_endpoint(
    service_id: str,
    endpoint_id: str,
    payload: EndpointInput,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> EndpointRecord:
    return registry.update_endpoint(service_id, endpoint_id, payload)


@router.delete("/services/{service_id}/endpoints/{endpoint_id}")
def delete_endpoint(
    service_id: str,
    endpoint_id: str,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> dict[str, Any]:
    registry.delete_endpoint(service_id, endpoint_id)
    return {"ok": True}


# ---- 手工端口 ---------------------------------------------------------------


@router.post(
    "/services/{service_id}/port-notes",
    response_model=PortNoteRecord,
    status_code=status.HTTP_201_CREATED,
)
def add_port_note(
    service_id: str,
    payload: PortNoteInput,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> PortNoteRecord:
    return registry.add_port_note(service_id, payload)


@router.delete("/services/{service_id}/port-notes/{note_id}")
def delete_port_note(
    service_id: str,
    note_id: str,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> dict[str, Any]:
    registry.delete_port_note(service_id, note_id)
    return {"ok": True}


# ---- GitHub 仓库 ------------------------------------------------------------


@router.put(
    "/services/{service_id}/release-source",
    response_model=ReleaseSourceRecord,
)
def set_release_source(
    service_id: str,
    payload: ReleaseSourceInput,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> ReleaseSourceRecord:
    return registry.set_release_source(service_id, payload)


@router.delete("/services/{service_id}/release-source")
def delete_release_source(
    service_id: str,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> dict[str, Any]:
    registry.delete_release_source(service_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# 发现
# ---------------------------------------------------------------------------


@router.get("/discovery")
def discovery_list(
    _: AuthDep,
    discovery: Annotated[DiscoveryService, Depends(get_discovery)],
    project: str = Query(default="", max_length=128),
    state: str = Query(default="", max_length=32),
    ignored: bool | None = Query(default=None),
    include_ephemeral: bool = Query(default=False),
) -> dict[str, Any]:
    items = discovery.candidates(
        project=project,
        state=state,
        ignored=ignored,
        include_ephemeral=include_ephemeral,
    )
    available, error = discovery.scan_available()
    return {
        "items": [item.model_dump() for item in items],
        "docker_available": available,
        "docker_error": error,
        "last_success_at": discovery.last_success_at(),
        "projects": sorted(
            {
                item.project
                for item in items
                if item.project
            }
        ),
    }


@router.post("/discovery/import")
def discovery_import(
    payload: DiscoveryImportRequest,
    _: WriteDep,
    discovery: Annotated[DiscoveryService, Depends(get_discovery)],
    store: Annotated[Store, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    result = discovery.import_components(payload)
    result["registry_revision"] = store.registry_revision
    return result


@router.patch("/discovery/decisions")
def discovery_decisions(
    payload: DiscoveryDecisionRequest,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
) -> dict[str, Any]:
    revision = registry.set_ignored(payload.source_keys, payload.ignored)
    return {"registry_revision": revision, "updated": len(payload.source_keys)}


@router.post("/discovery/scan")
async def discovery_scan(
    _: WriteDep,
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> JSONResponse:
    job, dedup = jobs.create(RefreshKind.DOCKER, None)
    import asyncio

    asyncio.create_task(jobs.run(job.id))
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={**job.model_dump(), "deduplicated": dedup},
    )


# ---------------------------------------------------------------------------
# 资源总览
# ---------------------------------------------------------------------------


@router.get("/resources/ports")
def resource_ports(
    _: AuthDep,
    resources: Annotated[ResourceProjector, Depends(get_resources)],
    only_registered: bool = Query(default=False),
    query: str = Query(default="", max_length=200),
    protocol: str = Query(default="", max_length=8),
) -> dict[str, Any]:
    return resources.ports(
        only_registered=only_registered, query=query, protocol=protocol
    )


@router.get("/resources/domains")
def resource_domains(
    _: AuthDep,
    resources: Annotated[ResourceProjector, Depends(get_resources)],
    query: str = Query(default="", max_length=200),
) -> dict[str, Any]:
    return resources.domains(query=query)


@router.get("/resources/certificates")
def resource_certificates(
    _: AuthDep,
    resources: Annotated[ResourceProjector, Depends(get_resources)],
    query: str = Query(default="", max_length=200),
) -> dict[str, Any]:
    return resources.certificates(query=query)


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------


@router.get("/services/{service_id}/releases", response_model=ReleaseListResponse)
def service_releases(
    service_id: str,
    _: AuthDep,
    registry: Annotated[Registry, Depends(get_registry)],
    checker: Annotated[Checker, Depends(get_checker)],
) -> ReleaseListResponse:
    source = registry.get_release_source_for_service(service_id)
    if source is None:
        return ReleaseListResponse(source=None, items=[], check=None)
    items = checker.releases.releases_for_source(
        source.id, source.owner, source.repo
    )
    state = checker.releases.sync_state(source.owner, source.repo) or {}
    return ReleaseListResponse(
        source=source,
        items=[
            ReleaseView(
                owner=item["owner"],
                repo=item["repo"],
                release_id=int(item["release_id"]),
                tag=item["tag"],
                name=item["name"],
                published_at=item["published_at"],
                body=item["body"],
                html_url=item["html_url"],
                read=bool(item["read"]),
            )
            for item in items
        ],
        check=checker.checks.get(
            target_type="service", target_id=service_id, check_kind="releases"
        ),
        truncated=bool(state.get("truncated")),
        latest_release_id=state.get("latest_release_id"),
    )


@router.post("/services/{service_id}/releases/read")
def mark_releases_read(
    service_id: str,
    payload: ReleaseReadRequest,
    _: WriteDep,
    registry: Annotated[Registry, Depends(get_registry)],
    checker: Annotated[Checker, Depends(get_checker)],
) -> dict[str, Any]:
    source = registry.get_release_source_for_service(service_id)
    if source is None:
        raise not_found("该服务未关联 GitHub 仓库")
    updated = checker.releases.mark_read(source.id, payload.release_ids)
    return {"updated": updated}


# ---------------------------------------------------------------------------
# 刷新任务
# ---------------------------------------------------------------------------


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest,
    _: WriteDep,
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> JSONResponse:
    job, dedup = jobs.create(payload.kind, payload.target_id)
    if not dedup:
        import asyncio

        asyncio.create_task(jobs.run(job.id))
    body = job.model_dump()
    body["deduplicated"] = dedup
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body)


@router.get("/jobs/{job_id}", response_model=RefreshJobView)
def get_job(
    job_id: str,
    _: AuthDep,
    jobs: Annotated[JobManager, Depends(get_jobs)],
) -> RefreshJobView:
    return jobs.get(job_id)


@router.get("/jobs")
def list_jobs(
    _: AuthDep,
    jobs: Annotated[JobManager, Depends(get_jobs)],
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    return {"items": [job.model_dump() for job in jobs.list(limit=limit)]}


# ---------------------------------------------------------------------------
# 备份
# ---------------------------------------------------------------------------


@router.get("/backup/export")
def backup_export(
    _: AuthDep, store: Annotated[Store, Depends(get_store)]
) -> JSONResponse:
    payload = export_payload(store)
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": 'attachment; filename="service-manager-backup.json"',
        },
    )


@router.post("/backup/preview", response_model=BackupPreviewResponse)
async def backup_preview(
    _: WriteDep,
    store: Annotated[Store, Depends(get_store)],
    file: UploadFile | None = None,
    request: Request = None,  # type: ignore[assignment]
) -> BackupPreviewResponse:
    raw = await _read_upload(file, request)
    try:
        result = preview(store, raw)
    except BackupError as exc:
        from src.errors import ApiError

        raise ApiError(400, exc.code, exc.message) from exc
    return BackupPreviewResponse(
        digest=result.digest,
        registry_revision=result.registry_revision,
        counts=result.counts,
        current_counts=result.current_counts,
        warnings=result.warnings,
    )


@router.post("/backup/restore")
async def backup_restore(
    _: WriteDep,
    store: Annotated[Store, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    digest: Annotated[str, Form()],
    registry_revision: Annotated[int, Form()],
    confirm: Annotated[bool, Form()] = False,
    file: UploadFile | None = None,
    request: Request = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """恢复：multipart 里带文件 + digest/revision/confirm 三个表单字段。

    与 /backup/preview 共用同一文件字节；digest 与 revision 必须与预览时一致，
    否则拒绝（防止「预览的是 A、恢复的是 B」）。
    """
    raw = await _read_upload(file, request)
    try:
        parsed = preview(store, raw)
        result = restore(
            store,
            payload=parsed.payload,
            expected_digest=digest,
            expected_revision=registry_revision,
            raw=raw,
            confirm=confirm,
            data_dir=settings.data_dir,
        )
    except BackupError as exc:
        from src.errors import ApiError

        raise ApiError(400, exc.code, exc.message) from exc
    return result


async def _read_upload(file: UploadFile | None, request: Request | None) -> bytes:
    if file is not None:
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
    elif request is not None:
        raw = await request.body()
    else:
        raise bad_request("缺少上传文件")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise too_large(f"文件超过 {MAX_UPLOAD_BYTES // 1024 // 1024} MiB")
    if not raw:
        raise bad_request("上传文件为空")
    return raw

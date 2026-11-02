"""REST API。

内部统一 /api 前缀；外部经 Nginx /api/index-trends/* 剥前缀转发（新服务接入契约）。
指数代码全链路字符串（code-type-guidelines）。
"""
from __future__ import annotations


from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from src import __version__
from src.core.models import (
    CURRENT_WEEKLY_MODEL_KINDS,
    LEGACY_KIND_TO_WEEKLY,
)
from src.services.trend_service import INDEX_CODE, WeeklyTrendService

router = APIRouter(prefix="/api")


class ReportSettingsPatch(BaseModel):
    model_kind: str | None = None
    enabled: bool | None = None
    send_cron: str | None = None
    channel: str | None = None


def get_service(request: Request) -> WeeklyTrendService:
    service = getattr(request.app.state, "trend_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="服务未初始化")
    return service


def _require_supported_index(code: str) -> None:
    if code != INDEX_CODE:
        raise HTTPException(status_code=404, detail=f"暂不支持指数: {code}（首版仅支持 {INDEX_CODE}）")


def _resolve_current_kind(kind: str) -> str:
    """旧月线 kind 只作为别名解析到周线，响应里的 timeframe 仍是 week。"""
    mapped = LEGACY_KIND_TO_WEEKLY.get(kind, kind)
    if mapped not in CURRENT_WEEKLY_MODEL_KINDS:
        raise HTTPException(status_code=400, detail=f"非法当前模型: {kind}")
    return mapped


_MONTHLY_MODEL_DETAIL = "该模型属于月线周期，不能用于周线图。请改用周线模型。"


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "index-trends", "version": __version__}


@router.get("/indices")
async def indices(request: Request) -> dict:
    return get_service(request).indices_overview()


@router.get("/indices/{code}/history")
async def history(code: str, request: Request) -> dict:
    _require_supported_index(code)
    return get_service(request).history_overview()


@router.get("/indices/{code}/chart")
async def chart(
    code: str,
    request: Request,
    model: str = Query(..., description="模型ID，或 kind:<当前模型种类> 取最新版本"),
    scope: str = Query("current", pattern="^(history|current)$"),
) -> dict:
    _require_supported_index(code)
    service = get_service(request)
    if model.startswith("kind:"):
        kind = _resolve_current_kind(model.split(":", 1)[1])
        target = service.store.latest_weekly_model(code, kind)
    else:
        target = service.weekly_model_by_id(model)
        if target is None and service.monthly_model_by_id(model) is not None:
            raise HTTPException(status_code=409, detail=_MONTHLY_MODEL_DETAIL)
    if target is None:
        raise HTTPException(status_code=404, detail=f"模型不存在: {model}")
    return service.build_chart(target, scope)


@router.get("/indices/{code}/status")
async def status(
    code: str,
    request: Request,
    model: str = Query(..., description="当前模型种类 trailing_10y_weekly|since_inception_weekly，旧月线 kind 仅作别名"),
) -> dict:
    _require_supported_index(code)
    kind = _resolve_current_kind(model)
    return get_service(request).current_status(kind)


@router.get("/report-settings")
async def get_report_settings(request: Request) -> dict:
    service = get_service(request)
    settings = service.store.get_report_settings()
    settings.pop("id", None)
    return settings   # 不含任何密钥字段


@router.patch("/report-settings")
async def patch_report_settings(patch: ReportSettingsPatch, request: Request) -> dict:
    service = get_service(request)
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}
    if "model_kind" in updates:
        mapped = LEGACY_KIND_TO_WEEKLY.get(updates["model_kind"], updates["model_kind"])
        if mapped not in CURRENT_WEEKLY_MODEL_KINDS:
            raise HTTPException(status_code=400, detail=f"非法模型种类: {updates['model_kind']}")
        updates["model_kind"] = mapped
    if "channel" in updates and updates["channel"] != "dingtalk":
        raise HTTPException(status_code=400, detail="首版仅支持 dingtalk 渠道")
    updated = service.store.update_report_settings(updates)
    updated.pop("id", None)
    return updated


@router.get("/reports")
async def list_reports(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    service = get_service(request)
    return {"reports": service.store.list_reports(limit), "total_returned": min(limit, 100)}


@router.post("/refresh")
async def refresh(request: Request) -> dict:
    service = get_service(request)
    from src.data.provider import ProviderError

    try:
        result = await service.refresh()
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))  # noqa: B904
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"数据校验失败: {e}")  # noqa: B904
    return {
        "success": result.success,
        "message": result.message,
        "data_cutoff_week": result.data_cutoff_week,
        "new_models": result.new_models,
        "weekly_count": result.weekly_count,
        "snapshot_id": result.snapshot_id,
    }


@router.post("/report-jobs/{job_id}/run")
async def run_report_job(job_id: str, request: Request) -> dict:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="调度器未初始化")
    try:
        return await scheduler.trigger(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"未知任务: {job_id}")  # noqa: B904
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))  # noqa: B904

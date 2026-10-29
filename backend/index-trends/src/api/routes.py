"""REST API。

内部统一 /api 前缀；外部经 Nginx /api/index-trends/* 剥前缀转发（新服务接入契约）。
指数代码全链路字符串（code-type-guidelines）。
"""
from __future__ import annotations


from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from src import __version__
from src.core.models import CURRENT_MODEL_KINDS, KIND_SINCE_INCEPTION
from src.services.trend_service import FUTURE_EXTENSION_MONTHS, INDEX_CODE, TrendService

router = APIRouter(prefix="/api")


class ReportSettingsPatch(BaseModel):
    model_kind: str | None = None
    enabled: bool | None = None
    send_cron: str | None = None
    channel: str | None = None


def get_service(request: Request) -> TrendService:
    service = getattr(request.app.state, "trend_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="服务未初始化")
    return service


def _require_supported_index(code: str) -> None:
    if code != INDEX_CODE:
        raise HTTPException(status_code=404, detail=f"暂不支持指数: {code}（首版仅支持 {INDEX_CODE}）")


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
        kind = model.split(":", 1)[1]
        if kind not in CURRENT_MODEL_KINDS:
            raise HTTPException(status_code=400, detail=f"非法当前模型: {kind}")
        target = service.store.latest_model(code, kind)
    else:
        target = next(
            (m for m in service.store.list_models(code) if m.model_id == model), None
        )
    if target is None:
        raise HTTPException(status_code=404, detail=f"模型不存在: {model}")
    extend_until: str | None
    if scope == "history":
        # 全历史回溯不延伸未来；固定窗口延伸到观察区实际截止
        if target.kind == KIND_SINCE_INCEPTION:
            extend_until = None
        else:
            extend_until = service._observation_end(target.fit_start, target.fit_end)
    else:
        from src.core import months as mutils

        extend_until = mutils.shift_month(target.fit_end, FUTURE_EXTENSION_MONTHS)
    return service.build_chart(target, extend_until)


@router.get("/indices/{code}/status")
async def status(
    code: str,
    request: Request,
    model: str = Query(..., description="当前模型种类 trailing_120m|since_inception"),
) -> dict:
    _require_supported_index(code)
    if model not in CURRENT_MODEL_KINDS:
        raise HTTPException(status_code=400, detail=f"非法当前模型: {model}")
    return get_service(request).current_status(model)


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
    if "model_kind" in updates and updates["model_kind"] not in CURRENT_MODEL_KINDS:
        raise HTTPException(status_code=400, detail=f"非法模型种类: {updates['model_kind']}")
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
        "data_cutoff_month": result.data_cutoff_month,
        "new_models": result.new_models,
        "monthly_count": result.monthly_count,
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

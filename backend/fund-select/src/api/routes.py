"""
API 路由定义（前缀 /api/funds）
"""
import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select

from src.api.models import (
    FundDetailResponse,
    RefreshResponse,
    RefreshStatusResponse,
    ScreenResponse,
    StatsResponse,
)
from src.db.models import Fund, FundFees, FundHoldingsBond, FundPerformance, RefreshRun
from src.db.session import get_db
from src.scheduler.tasks import refresh_configured_funds_sync
from src.services.export_service import export_csv
from src.services.filter_service import FilterService
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.api")

router = APIRouter()


@router.get("/health", tags=["system"])
async def health():
    """健康检查"""
    return {"status": "ok"}


@router.get("/screen", response_model=ScreenResponse)
async def screen(
    min_age: Optional[float] = Query(None, ge=0, le=100, description="成立年限 ≥ X（年）"),
    min_size_yi: Optional[float] = Query(None, ge=0, le=10000, description="规模 ≥ Y（亿）"),
    max_dd_3y: Optional[float] = Query(None, ge=0, le=100, description="近 3 年最大回撤 ≤ Z%（绝对值）"),
    min_mgr_exp: Optional[float] = Query(None, ge=0, le=100, description="经理从业年限 ≥ W（年）"),
    sort: str = Query("size_yi", description="排序字段"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db=Depends(get_db),
):
    """筛选（不分页，v1 名单仅 31 只）"""
    if sort not in ("size_yi", "age_years", "mgr_experience_years", "dd_3y",
                    "ret_1y", "ret_3y", "ret_5y", "fee_annual", "code"):
        raise HTTPException(status_code=422, detail=f"不支持的排序字段: {sort}")
    svc = FilterService(db)
    return svc.screen(
        min_age=min_age,
        min_size_yi=min_size_yi,
        max_dd_3y=max_dd_3y,
        min_mgr_exp=min_mgr_exp,
        sort=sort,
        order=order,
    )


@router.get("/export/csv")
async def export_csv_route(
    min_age: Optional[float] = Query(None, ge=0, le=100),
    min_size_yi: Optional[float] = Query(None, ge=0, le=10000),
    max_dd_3y: Optional[float] = Query(None, ge=0, le=100),
    min_mgr_exp: Optional[float] = Query(None, ge=0, le=100),
    sort: str = Query("size_yi"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db=Depends(get_db),
):
    """导出当前筛选结果 CSV（UTF-8 BOM，文件名含日期）"""
    filters = {
        "min_age": min_age, "min_size_yi": min_size_yi, "max_dd_3y": max_dd_3y,
        "min_mgr_exp": min_mgr_exp, "sort": sort, "order": order,
    }
    content, filename = export_csv(filters, FilterService(db))
    return Response(
        content="﻿" + content,  # BOM
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/refresh/status", response_model=RefreshStatusResponse)
async def refresh_status(
    task_id: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """查询刷新进度（无 task_id 返回最近一次）"""
    q = select(RefreshRun)
    if task_id:
        q = q.where(RefreshRun.task_id == task_id)
    else:
        q = q.order_by(RefreshRun.started_at.desc()).limit(1)
    run = db.execute(q).scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="无刷新记录")
    errors = []
    if run.errors:
        try:
            errors = json.loads(run.errors)
        except (json.JSONDecodeError, TypeError):
            errors = []
    return RefreshStatusResponse(
        task_id=run.task_id, status=run.status, total=run.total,
        completed=run.completed, failed=run.failed, errors=errors,
    )


@router.get("/refresh", response_model=RefreshResponse)
async def refresh(
    background: BackgroundTasks,
    limit: Optional[int] = Query(None, ge=1, le=100),
):
    """手动触发刷新（后台执行，返回 task_id）"""
    import uuid
    task_id = str(uuid.uuid4())
    background.add_task(refresh_configured_funds_sync, limit=limit, preset_task_id=task_id)
    return RefreshResponse(task_id=task_id, status="started")


@router.get("/stats", response_model=StatsResponse)
async def stats(db=Depends(get_db)):
    """库内数据概况"""
    total = db.execute(select(func.count()).select_from(Fund).where(Fund.is_active == True)).scalar() or 0  # noqa: E712
    with_perf = db.execute(select(func.count()).select_from(FundPerformance)).scalar() or 0
    with_fees = db.execute(select(func.count()).select_from(FundFees)).scalar() or 0
    with_hold = db.execute(select(func.count()).select_from(FundHoldingsBond)).scalar() or 0
    last_run = db.execute(
        select(RefreshRun).order_by(RefreshRun.started_at.desc()).limit(1)
    ).scalars().first()
    return StatsResponse(
        total=total,
        with_performance=with_perf,
        with_fees=with_fees,
        with_holdings=with_hold,
        last_refresh_at=last_run.finished_at if last_run else None,
    )


@router.get("/{code}", response_model=FundDetailResponse)
async def fund_detail(code: str, db=Depends(get_db)):
    """单只基金详情"""
    detail = FilterService(db).get_detail(code)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"基金不存在: {code}")
    return detail

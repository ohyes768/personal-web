"""
API 路由定义

主路由：/api/funds/*（债基，对应 /funds，宇宙 = funds.yaml）
股票路由：/api/funds/stock/*（对应 /funds/stock，宇宙 = funds_stock.yaml）
"""
import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select

from src.api.models import (
    AchievementRankDTO,
    FundDetailResponse,
    RefreshResponse,
    RefreshStatusResponse,
    ScreenResponse,
    StatsResponse,
)
from src.db.models import (
    FundAchievementRank,
    RefreshRun,
)
from src.db.session import get_db
from src.scheduler.tasks import refresh_configured_funds_sync, refresh_stock_funds_sync
from src.services.filter_service import FilterService
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.api")

router = APIRouter()
router_stock = APIRouter(prefix="/stock", tags=["stock"])


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
    exclude_qdii: bool = Query(False, description="排除 fund_type 以 QDII 开头或互认基金"),
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
        exclude_qdii=exclude_qdii,
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
    """债基 tab 库内概况（funds.yaml ∩ is_active）"""
    counts = FilterService(db).universe_stats("bond")
    last_run = db.execute(
        select(RefreshRun).order_by(RefreshRun.started_at.desc()).limit(1)
    ).scalars().first()
    return StatsResponse(
        **counts,
        last_refresh_at=last_run.finished_at if last_run else None,
    )


@router.get("/{code}", response_model=FundDetailResponse)
async def fund_detail(code: str, db=Depends(get_db)):
    """单只基金详情"""
    detail = FilterService(db).get_detail(code)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"基金不存在: {code}")
    return detail


# ──────────────────────────────────────────────────────────────────
# 股票 tab 路由（/api/funds/stock/*）
# 与现有 /api/funds/* 平列；成员 = funds_stock.yaml ∩ is_active
# ──────────────────────────────────────────────────────────────────

def _stock_screen_params(
    min_age: Optional[float] = Query(None, ge=0, le=100),
    min_size_yi: Optional[float] = Query(None, ge=0, le=10000),
    max_dd_3y: Optional[float] = Query(None, ge=0, le=100),
    min_mgr_exp: Optional[float] = Query(None, ge=0, le=100),
    sort: str = Query("ret_5y"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """股票筛选参数共享"""
    return {
        "min_age": min_age, "min_size_yi": min_size_yi,
        "max_dd_3y": max_dd_3y, "min_mgr_exp": min_mgr_exp,
        "sort": sort, "order": order,
    }


@router_stock.get("/screen", response_model=ScreenResponse)
async def stock_screen(
    min_age: Optional[float] = Query(None, ge=0, le=100),
    min_size_yi: Optional[float] = Query(None, ge=0, le=10000),
    max_dd_3y: Optional[float] = Query(None, ge=0, le=100),
    min_mgr_exp: Optional[float] = Query(None, ge=0, le=100),
    min_sharpe: Optional[float] = Query(None, ge=-10, le=10, description="夏普 ≥ X（近 3 年）"),
    sort: str = Query("ret_5y"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    exclude_qdii: bool = Query(False, description="排除 fund_type 以 QDII 开头或互认基金"),
    db=Depends(get_db),
):
    """股票 tab 筛选（funds_stock.yaml ∩ is_active）"""
    return FilterService(db).screen_stock(
        min_age=min_age, min_size_yi=min_size_yi,
        max_dd_3y=max_dd_3y, min_mgr_exp=min_mgr_exp, min_sharpe=min_sharpe,
        sort=sort, order=order, exclude_qdii=exclude_qdii,
    )


@router_stock.get("/refresh", response_model=RefreshResponse)
async def stock_refresh(
    background: BackgroundTasks,
    limit: Optional[int] = Query(None, ge=1, le=100),
):
    """手动触发股票 tab 名单刷新（后台执行）"""
    import uuid
    task_id = str(uuid.uuid4())
    background.add_task(refresh_stock_funds_sync, limit=limit, preset_task_id=task_id)
    return RefreshResponse(task_id=task_id, status="started")


@router_stock.get("/refresh/status", response_model=RefreshStatusResponse)
async def stock_refresh_status(
    task_id: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """股票 tab 刷新进度（复用 RefreshRun 表）"""
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


@router_stock.get("/stats", response_model=StatsResponse)
async def stock_stats(db=Depends(get_db)):
    """股票 tab 库内概况（funds_stock.yaml ∩ is_active）"""
    counts = FilterService(db).universe_stats("stock")
    last_run = db.execute(
        select(RefreshRun).order_by(RefreshRun.started_at.desc()).limit(1)
    ).scalars().first()
    return StatsResponse(
        **counts,
        last_refresh_at=last_run.finished_at if last_run else None,
    )


@router_stock.get("/{code}", response_model=FundDetailResponse)
async def stock_fund_detail(code: str, db=Depends(get_db)):
    """单只股票基金详情（含业绩排名）"""
    base_detail = FilterService(db).get_detail(code)
    if base_detail is None:
        raise HTTPException(status_code=404, detail=f"基金不存在: {code}")
    # 附加 achievement_ranks
    rows = db.execute(
        select(FundAchievementRank)
        .where(FundAchievementRank.code == code)
        .order_by(FundAchievementRank.period_kind, FundAchievementRank.period)
    ).scalars().all()
    base_detail["achievement_ranks"] = [
        AchievementRankDTO(
            period_kind=r.period_kind,
            period=r.period,
            ret=r.ret,
            peer_rank=r.peer_rank,
        )
        for r in rows
    ]
    return base_detail

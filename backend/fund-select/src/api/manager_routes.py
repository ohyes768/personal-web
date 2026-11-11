"""经理维度 API（/api/funds/managers/*，任务 11-10-fund-manager-evaluation）。

独立于基金 /screen 系列；注册顺序在通用 /{code} 之前（见 main.py 注释）。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.models import (
    ManagerDetailResponse,
    ManagerScreenResponse,
)
from src.db.session import get_db
from src.services.manager_service import ManagerService

router_managers = APIRouter(prefix="/managers", tags=["managers"])
# main.py 统一以 `router` 命名导入（与其他路由模块一致）
router = router_managers

VALID_SORTS = ("career_years", "weighted_annual", "max_drawdown", "sharpe",
               "calmar", "current_scale_yi", "managed_fund_count", "name")


@router_managers.get("/screen", response_model=ManagerScreenResponse)
async def manager_screen(
    min_career_years: Optional[float] = Query(None, ge=0, le=100, description="从业年限 ≥"),
    min_weighted_annual: Optional[float] = Query(None, ge=-100, le=1000, description="任职加权年化 ≥ %"),
    max_drawdown: Optional[float] = Query(None, ge=0, le=100, description="最大回撤 ≤ %（绝对值）"),
    min_scale_yi: Optional[float] = Query(None, ge=0, le=100000, description="在管规模 ≥ 亿"),
    min_sharpe: Optional[float] = Query(None, ge=-10, le=100, description="夏普 ≥"),
    keyword: Optional[str] = Query(None, max_length=50, description="姓名/公司模糊匹配"),
    sort: str = Query("weighted_annual", description="排序字段"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    """经理列表（筛选 + 分页）。total = 筛后总数，与 page/limit 无关。"""
    if sort not in VALID_SORTS:
        raise HTTPException(status_code=422, detail=f"不支持的排序字段: {sort}")
    svc = ManagerService(db)
    return svc.screen(
        min_career_years=min_career_years,
        min_weighted_annual=min_weighted_annual,
        max_drawdown=max_drawdown,
        min_scale_yi=min_scale_yi,
        min_sharpe=min_sharpe,
        keyword=keyword,
        sort=sort,
        order=order,
        page=page,
        limit=limit,
    )


@router_managers.get("/{manager_id}", response_model=ManagerDetailResponse)
async def manager_detail(manager_id: str, db=Depends(get_db)):
    """经理详情（含历任基金，含已离任）。"""
    detail = ManagerService(db).get_detail(manager_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"经理不存在: {manager_id}")
    return detail

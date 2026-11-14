"""夏普榜单只读 API（GET /api/funds/sharpe-board）

⚠ 注册顺序：本 router 必须在通用详情 router（src/api/routes.py 的
/{code} 路由）之前 include（src/main.py）——FastAPI 按注册顺序匹配，
后注册会让 /api/funds/sharpe-board 被 /{code} 吞掉当基金代码查（404）。

参数与统计合同见任务 design「API 与统计合同」：
- source 默认 discovery-stock（股基·市场）；profile_version 未知 → 404
- min_latest_sharpe 是展示下限（最近一次上榜值，含等于），与记录规则
  min_sharpe=0.8 分开（R5）
- range 只裁周历（图），不改累计周数/最近上榜值/命中集合（R5/AC4）
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.models import SharpeBoardResponse
from src.db.session import get_db
from src.services.sharpe_board_service import aggregate_board, get_profile

router = APIRouter(tags=["sharpe-board"])


@router.get("/sharpe-board", response_model=SharpeBoardResponse)
async def sharpe_board(
    source: str = Query(
        "discovery-stock", pattern="^(all|stock|discovery-stock)$",
        description="榜单来源：stock=股基·雪球三分法，discovery-stock=股基·市场，all=两者聚合",
    ),
    profile_version: str = Query("v3", min_length=1, max_length=16, description="规则版本"),
    min_latest_sharpe: Optional[float] = Query(
        None, ge=-10, le=10,
        description="最近上榜夏普下限（含等于；按全历史最近一次上榜值判断，R5）",
    ),
    min_weeks: int = Query(1, ge=1, description="至少上榜几周（全历史累计）"),
    latest_only: bool = Query(False, description="只看最新成功（complete）一周在榜的基金"),
    range: str = Query("all", pattern="^(3m|6m|1y|all)$",
                       description="图时间范围（只裁图，不改统计与命中集合）"),
    page: int = Query(1, ge=1, description="页码，1-indexed"),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    db=Depends(get_db),
):
    """夏普榜单：列表（分页）+ 统一周历 + 全部命中基金的曲线序列"""
    try:
        if source == "all":
            get_profile("stock", profile_version)  # all 复用同一 version 存在性校验
        else:
            get_profile(source, profile_version)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"未知榜单来源/规则版本: {source}/{profile_version}",
        )
    return aggregate_board(
        db,
        source=source,
        profile_version=profile_version,
        min_latest_sharpe=min_latest_sharpe,
        min_weeks=min_weeks,
        latest_only=latest_only,
        range_key=range,
        page=page,
        limit=limit,
    )

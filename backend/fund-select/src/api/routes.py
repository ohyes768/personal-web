"""
API 路由定义

主路由：/api/funds/*（债基，对应 /funds，宇宙 = funds.yaml）
股票路由：/api/funds/stock/*（对应 /funds/stock，宇宙 = funds_stock.yaml）
市场路由：/api/funds/discovery-bond/* 与 /api/funds/discovery-stock/*（对应 /funds/discovery-*，
          宇宙 = akshare market_type 粗分类）
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
from src.scheduler.tasks import (
    refresh_configured_funds_sync,
    refresh_market_universe_sync,
    refresh_stock_funds_sync,
)
# refresh_market_full_sync 单独 import（避免 tasks.py 循环依赖 market_full_pipeline）
from src.services.filter_service import FilterService
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.api")

router = APIRouter()
router_stock = APIRouter(prefix="/stock", tags=["stock"])
router_discovery_bond = APIRouter(prefix="/discovery-bond", tags=["discovery-bond"])
router_discovery_stock = APIRouter(prefix="/discovery-stock", tags=["discovery-stock"])


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


# ──────────────────────────────────────────────────────────────────
# 市场 tab 路由（/api/funds/discovery-{bond,stock}/*）
# 成员 = market_type ∈ DEFAULT_DISCOVERY_UNIVERSE ∩ is_active
# 单只详情复用 /api/funds/{code}（设计决策 D2）
# ──────────────────────────────────────────────────────────────────


def _parse_market_types(raw: Optional[str]) -> list[str] | None:
    """查询串 '债券型,定开债券' → ['债券型','定开债券']；None/空 → None（走默认）"""
    if not raw:
        return None
    out = [s.strip() for s in raw.split(",") if s.strip()]
    return out if out else None


@router_discovery_bond.get("/screen", response_model=ScreenResponse)
async def discovery_bond_screen(
    min_age: Optional[float] = Query(None, ge=0, le=100),
    min_size_yi: Optional[float] = Query(None, ge=0, le=10000),
    max_dd_3y: Optional[float] = Query(None, ge=0, le=100),
    min_mgr_exp: Optional[float] = Query(None, ge=0, le=100),
    min_sharpe: Optional[float] = Query(None, ge=-10, le=10),
    min_ret_1y: Optional[float] = Query(None, description="近 1 年涨跌幅 ≥ X%（隐式要求成立 ≥ 1 年）"),
    min_ret_3y: Optional[float] = Query(None, description="近 3 年涨跌幅 ≥ X%（隐式要求成立 ≥ 3 年）"),
    max_nav_stale_days: Optional[int] = Query(None, ge=0, description="净值日距今 ≤ N 天（排除疑似清盘）"),
    sort: str = Query("size_yi"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    exclude_qdii: bool = Query(False),
    market_type: Optional[str] = Query(None, description="akshare 基金类型，CSV；空 = 走默认 universe"),
    db=Depends(get_db),
):
    """债基·市场 tab 筛选（market_type 默认 = 10 个债券相关子类）"""
    return FilterService(db).screen_discovery_bond(
        min_age=min_age, min_size_yi=min_size_yi,
        max_dd_3y=max_dd_3y, min_mgr_exp=min_mgr_exp, min_sharpe=min_sharpe,
        min_ret_1y=min_ret_1y, min_ret_3y=min_ret_3y,
        max_nav_stale_days=max_nav_stale_days,
        sort=sort, order=order, exclude_qdii=exclude_qdii,
        market_types=_parse_market_types(market_type),
    )


@router_discovery_bond.get("/refresh", response_model=RefreshResponse)
async def discovery_bond_refresh(
    background: BackgroundTasks,
    limit: Optional[int] = Query(None, ge=1, le=100),
):
    """手动触发全市场名单 refresh（discovery-bond / discovery-stock 共用）"""
    import uuid
    task_id = str(uuid.uuid4())
    background.add_task(refresh_market_universe_sync, preset_task_id=task_id)
    return RefreshResponse(task_id=task_id, status="started")


@router_discovery_bond.get("/refresh/status", response_model=RefreshStatusResponse)
async def discovery_bond_refresh_status(
    task_id: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """市场名单刷新进度（复用 RefreshRun）"""
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


@router_discovery_bond.get("/stats", response_model=StatsResponse)
async def discovery_bond_stats(db=Depends(get_db)):
    """债基·市场 tab 库内概况（market_type ∩ is_active）"""
    counts = FilterService(db).universe_stats("discovery-bond")
    last_run = db.execute(
        select(RefreshRun).order_by(RefreshRun.started_at.desc()).limit(1)
    ).scalars().first()
    return StatsResponse(
        **counts,
        last_refresh_at=last_run.finished_at if last_run else None,
    )


@router_discovery_stock.get("/screen", response_model=ScreenResponse)
async def discovery_stock_screen(
    min_age: Optional[float] = Query(None, ge=0, le=100),
    min_size_yi: Optional[float] = Query(None, ge=0, le=10000),
    max_dd_3y: Optional[float] = Query(None, ge=0, le=100),
    min_mgr_exp: Optional[float] = Query(None, ge=0, le=100),
    min_sharpe: Optional[float] = Query(None, ge=-10, le=10),
    min_ret_1y: Optional[float] = Query(None, description="近 1 年涨跌幅 ≥ X%（隐式要求成立 ≥ 1 年）"),
    min_ret_3y: Optional[float] = Query(None, description="近 3 年涨跌幅 ≥ X%（隐式要求成立 ≥ 3 年）"),
    max_nav_stale_days: Optional[int] = Query(None, ge=0, description="净值日距今 ≤ N 天（排除疑似清盘）"),
    sort: str = Query("ret_5y"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    exclude_qdii: bool = Query(False),
    market_type: Optional[str] = Query(None, description="akshare 基金类型，CSV；空 = 走默认 universe"),
    db=Depends(get_db),
):
    """股基·市场 tab 筛选（market_type 默认 = 5 个粗类别：股票型/混合型/指数型/QDII/REITs）"""
    return FilterService(db).screen_discovery_stock(
        min_age=min_age, min_size_yi=min_size_yi,
        max_dd_3y=max_dd_3y, min_mgr_exp=min_mgr_exp, min_sharpe=min_sharpe,
        min_ret_1y=min_ret_1y, min_ret_3y=min_ret_3y,
        max_nav_stale_days=max_nav_stale_days,
        sort=sort, order=order, exclude_qdii=exclude_qdii,
        market_types=_parse_market_types(market_type),
    )


@router_discovery_stock.get("/refresh", response_model=RefreshResponse)
async def discovery_stock_refresh(
    background: BackgroundTasks,
    limit: Optional[int] = Query(None, ge=1, le=100),
):
    """手动触发全市场名单 refresh（与 discovery-bond 共用同一 task）"""
    import uuid
    task_id = str(uuid.uuid4())
    background.add_task(refresh_market_universe_sync, preset_task_id=task_id)
    return RefreshResponse(task_id=task_id, status="started")


@router_discovery_stock.get("/refresh/status", response_model=RefreshStatusResponse)
async def discovery_stock_refresh_status(
    task_id: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """市场名单刷新进度（复用 RefreshRun；与 discovery-bond 共用）"""
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


@router_discovery_stock.get("/stats", response_model=StatsResponse)
async def discovery_stock_stats(db=Depends(get_db)):
    """股基·市场 tab 库内概况（market_type ∩ is_active）"""
    counts = FilterService(db).universe_stats("discovery-stock")
    last_run = db.execute(
        select(RefreshRun).order_by(RefreshRun.started_at.desc()).limit(1)
    ).scalars().first()
    return StatsResponse(
        **counts,
        last_refresh_at=last_run.finished_at if last_run else None,
    )


# ──────────────────────────────────────────────────────────────────
# 市场 tab 全量 refresh（4 阶段流水线：rankhandler + fund_basic + nav + risk）
# 手动触发，预筛选参数缩小 universe
# ──────────────────────────────────────────────────────────────────


@router_discovery_bond.get("/full/refresh", response_model=RefreshResponse)
async def discovery_bond_full_refresh(
    background: BackgroundTasks,
    min_ret_1y: Optional[float] = Query(None, description="近 1 年涨跌幅 ≥ X%（L1 字段）"),
    min_ret_3y: Optional[float] = Query(None, description="近 3 年涨跌幅 ≥ X%（L1 字段）"),
    max_nav_stale_days: Optional[int] = Query(None, ge=0, description="净值日距今 ≤ N 天（L1 字段）"),
):
    """手动触发债基·市场全量 refresh（4 阶段流水线）

    预筛用 L1 业绩字段（min_ret_1y / min_ret_3y / max_nav_stale_days）——
    L2 字段（min_age / min_size_yi / min_mgr_exp）99% 是 NULL，做预筛会砍到 0，不可用。
    """
    import uuid
    from src.data.market_subtype_map import DISCOVERY_BOND_SUBTYPES
    from src.services.market_full_pipeline import refresh_market_full_sync
    task_id = str(uuid.uuid4())
    background.add_task(
        refresh_market_full_sync,
        universe_filter=list(DISCOVERY_BOND_SUBTYPES),
        min_ret_1y=min_ret_1y, min_ret_3y=min_ret_3y,
        max_nav_stale_days=max_nav_stale_days,
        preset_task_id=task_id,
    )
    return RefreshResponse(task_id=task_id, status="started")


@router_discovery_bond.get("/full/refresh/status", response_model=RefreshStatusResponse)
async def discovery_bond_full_refresh_status(
    task_id: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """全量 refresh 进度（查主 task 的 RefreshRun 记录；sub-task ID 自动 fallback）"""
    q = select(RefreshRun)
    if task_id:
        # 先查主 task；查不到再查 sub-task（id prefix 匹配）
        q = q.where(RefreshRun.task_id == task_id)
        run = db.execute(q).scalars().first()
        if run is None:
            # fallback: 查同前缀的 sub-task 列表（取最后一条）
            sub_q = select(RefreshRun).where(
                RefreshRun.task_id.like(f"{task_id}_%")
            ).order_by(RefreshRun.started_at.desc()).limit(1)
            run = db.execute(sub_q).scalars().first()
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


@router_discovery_stock.get("/full/refresh", response_model=RefreshResponse)
async def discovery_stock_full_refresh(
    background: BackgroundTasks,
    min_ret_1y: Optional[float] = Query(None, description="近 1 年涨跌幅 ≥ X%（L1 字段）"),
    min_ret_3y: Optional[float] = Query(None, description="近 3 年涨跌幅 ≥ X%（L1 字段）"),
    max_nav_stale_days: Optional[int] = Query(None, ge=0, description="净值日距今 ≤ N 天（L1 字段）"),
):
    """手动触发股基·市场全量 refresh（4 阶段流水线）

    预筛用 L1 业绩字段（min_ret_1y / min_ret_3y / max_nav_stale_days）——
    L2 字段（min_age / min_size_yi / min_mgr_exp）99% 是 NULL，做预筛会砍到 0，不可用。
    """
    import uuid
    from src.data.market_subtype_map import DISCOVERY_STOCK_SUBTYPES
    from src.services.market_full_pipeline import refresh_market_full_sync
    task_id = str(uuid.uuid4())
    background.add_task(
        refresh_market_full_sync,
        universe_filter=list(DISCOVERY_STOCK_SUBTYPES),
        min_ret_1y=min_ret_1y, min_ret_3y=min_ret_3y,
        max_nav_stale_days=max_nav_stale_days,
        preset_task_id=task_id,
    )
    return RefreshResponse(task_id=task_id, status="started")


@router_discovery_stock.get("/full/refresh/status", response_model=RefreshStatusResponse)
async def discovery_stock_full_refresh_status(
    task_id: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """股基·市场全量 refresh 进度（复用 RefreshRun；sub-task fallback 同 bond）"""
    q = select(RefreshRun)
    if task_id:
        q = q.where(RefreshRun.task_id == task_id)
        run = db.execute(q).scalars().first()
        if run is None:
            sub_q = select(RefreshRun).where(
                RefreshRun.task_id.like(f"{task_id}_%")
            ).order_by(RefreshRun.started_at.desc()).limit(1)
            run = db.execute(sub_q).scalars().first()
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

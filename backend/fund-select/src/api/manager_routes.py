"""经理维度 API（/api/funds/managers/*，任务 11-10-fund-manager-evaluation）。

独立于基金 /screen 系列；注册顺序在通用 /{code} 之前（见 main.py 注释）。

刷新端点（任务 11-11-fund-manager-tab-refresh）：
- 与基金 /refresh 同构：BackgroundTasks + task_id，进度写 RefreshRun 供 /status 轮询
- 必须注册在 /{manager_id} 之前，否则 "/refresh" 会被当成经理 ID 吞掉
"""
import json
import threading
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select

from src.api.models import (
    ManagerDetailResponse,
    ManagerScreenResponse,
    RefreshResponse,
    RefreshStatusResponse,
)
from src.db.models import RefreshRun
from src.db.session import get_db
from src.services.manager_service import ManagerService

router_managers = APIRouter(prefix="/managers", tags=["managers"])
# main.py 统一以 `router` 命名导入（与其他路由模块一致）
router = router_managers

VALID_SORTS = ("career_years", "weighted_annual", "max_drawdown", "sharpe",
               "calmar", "current_scale_yi", "managed_fund_count",
               "longest_tenure_years", "tenure_win_rate", "solo_ratio", "name")

# 单飞：经理全量采集要跑 20-40 分钟，重复点击只应有一次在跑
_refresh_lock = threading.Lock()


def _run_manager_refresh(task_id: str, max_managers: Optional[int]) -> None:
    """后台任务体：独立 Session（BackgroundTasks 与请求的 session 生命周期不同）。"""
    from src.db.session import SessionLocal
    from src.services.manager_refresh import refresh as refresh_managers
    from src.utils.logger import setup_logger

    logger = setup_logger("fund-select.manager_refresh.task")
    db = SessionLocal()
    try:
        # force=True：每次刷新都重采全部 scope 内经理，否则第二次点会空转
        refresh_managers(db, task_id=task_id, max_managers=max_managers, force=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("经理采集失败 task=%s", task_id)
        db.rollback()
        run = db.get(RefreshRun, task_id)
        if run is not None:
            run.status = "error"
            run.errors = json.dumps([str(exc)[:200]], ensure_ascii=False)
            db.commit()
    finally:
        db.close()
        _refresh_lock.release()


@router_managers.get("/refresh", response_model=RefreshResponse)
async def manager_refresh(
    background: BackgroundTasks,
    limit: Optional[int] = Query(None, ge=1, le=5000, description="只采前 N 人（调试用）"),
):
    """手动触发经理全量采集（后台执行，返回 task_id）。

    每次都是全量重采（force）：档案页的任职变更、新发/离任基金靠这个更新。
    并发保护：已有采集在跑时返回 409，不重复起任务。
    """
    if not _refresh_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="经理采集正在进行，请等待本轮结束")
    task_id = str(uuid.uuid4())
    try:
        db = _open_run(task_id)
        db.close()
    except Exception:
        _refresh_lock.release()
        raise
    background.add_task(_run_manager_refresh, task_id, limit)
    return RefreshResponse(task_id=task_id, status="started")


def _open_run(task_id: str):
    """预建 RefreshRun 行：客户端拿到 task_id 立刻能轮询到 running。"""
    from src.db.session import SessionLocal

    db = SessionLocal()
    db.add(RefreshRun(task_id=task_id, status="running", total=0))
    db.commit()
    return db


@router_managers.get("/refresh/status", response_model=RefreshStatusResponse)
async def manager_refresh_status(
    task_id: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """经理采集进度（task_id 为空时返回最近一次）。"""
    q = select(RefreshRun)
    if task_id:
        q = q.where(RefreshRun.task_id == task_id)
    else:
        q = q.order_by(RefreshRun.started_at.desc()).limit(1)
    run = db.execute(q).scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="无刷新记录")
    errors: list[str] = []
    if run.errors:
        try:
            parsed = json.loads(run.errors)
            errors = parsed if isinstance(parsed, list) else [str(parsed)]
        except (json.JSONDecodeError, TypeError):
            errors = [run.errors]
    return RefreshStatusResponse(
        task_id=run.task_id, status=run.status, total=run.total,
        completed=run.completed, failed=run.failed, errors=errors,
    )


@router_managers.get("/screen", response_model=ManagerScreenResponse)
async def manager_screen(
    min_career_years: Optional[float] = Query(None, ge=0, le=100, description="从业年限 ≥"),
    min_weighted_annual: Optional[float] = Query(None, ge=-100, le=1000, description="任职加权年化 ≥ %"),
    max_drawdown: Optional[float] = Query(None, ge=0, le=100, description="最大回撤 ≤ %（绝对值）"),
    min_scale_yi: Optional[float] = Query(None, ge=0, le=100000, description="在管规模 ≥ 亿"),
    min_sharpe: Optional[float] = Query(None, ge=-10, le=100, description="夏普 ≥"),
    min_win_rate: Optional[float] = Query(None, ge=0, le=100, description="任期胜率 ≥ %"),
    min_solo_ratio: Optional[float] = Query(None, ge=0, le=100, description="独管比例 ≥ %"),
    max_fund_count: Optional[int] = Query(None, ge=1, le=200, description="在管基金数 ≤ N"),
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
        min_win_rate=min_win_rate,
        min_solo_ratio=min_solo_ratio,
        max_fund_count=max_fund_count,
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

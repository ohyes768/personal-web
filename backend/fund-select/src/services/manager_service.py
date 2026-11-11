"""经理筛选服务（/api/funds/managers，任务 11-10-fund-manager-evaluation）。

以 managers 表为主体聚合排序；与基金 /screen 完全独立，不改其语义。
分页契约与 FilterService 对齐：total = 筛后总数，items = 当页，None 值排尾部。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.db.models import Manager, ManagerTenure


# 排序白名单（防注入；键 → (列, 默认方向)）
SORT_COLUMNS: dict[str, tuple] = {
    "career_years": (Manager.career_years, "desc"),
    "weighted_annual": (Manager.tenure_weighted_annual, "desc"),
    "max_drawdown": (Manager.max_drawdown, "asc"),     # 回撤负值，绝对值小在前
    "sharpe": (Manager.sharpe, "desc"),
    "calmar": (Manager.calmar, "desc"),
    "current_scale_yi": (Manager.current_scale_yi, "desc"),
    "managed_fund_count": (Manager.managed_fund_count, "asc"),
    "longest_tenure_years": (Manager.longest_tenure_years, "desc"),
    "name": (Manager.name, "asc"),
}


class ManagerService:
    def __init__(self, db: Session):
        self.db = db

    def screen(
        self,
        *,
        min_career_years: Optional[float] = None,
        min_weighted_annual: Optional[float] = None,
        max_drawdown: Optional[float] = None,      # 绝对值阈值，如 60 → mdd >= -60
        min_scale_yi: Optional[float] = None,
        min_sharpe: Optional[float] = None,
        keyword: Optional[str] = None,             # 姓名/公司模糊
        sort: str = "weighted_annual",
        order: str = "desc",
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        q = select(Manager).where(Manager.scope == "stock_active")

        if keyword:
            like = f"%{keyword}%"
            q = q.where(or_(Manager.name.like(like), Manager.company.like(like)))
        # NULL 一律不命中（与基金筛选语义一致）
        if min_career_years is not None:
            q = q.where(Manager.career_years >= min_career_years)
        if min_weighted_annual is not None:
            q = q.where(Manager.tenure_weighted_annual >= min_weighted_annual)
        if max_drawdown is not None:
            # 库内为负值（如 -45.2），用户输入按绝对值
            q = q.where(Manager.max_drawdown >= -abs(max_drawdown))
        if min_scale_yi is not None:
            q = q.where(Manager.current_scale_yi >= min_scale_yi)
        if min_sharpe is not None:
            q = q.where(Manager.sharpe >= min_sharpe)

        rows = self.db.execute(q).scalars().all()
        items = [self._to_dto(m) for m in rows]

        _col, default_desc = SORT_COLUMNS.get(sort, SORT_COLUMNS["weighted_annual"])
        descending = (order != "asc") if sort in SORT_COLUMNS else default_desc
        getter = {
            "career_years": lambda it: it["career_years"],
            "weighted_annual": lambda it: it["weighted_annual"],
            "max_drawdown": lambda it: None if it["max_drawdown"] is None else -abs(it["max_drawdown"]),
            "sharpe": lambda it: it["sharpe"],
            "calmar": lambda it: it["calmar"],
            "current_scale_yi": lambda it: it["current_scale_yi"],
            "managed_fund_count": lambda it: None if it["managed_fund_count"] is None else -it["managed_fund_count"],
            "longest_tenure_years": lambda it: it["longest_tenure_years"],
            "name": lambda it: it["name"],
        }.get(sort, lambda it: it["weighted_annual"])

        valued = [it for it in items if getter(it) is not None]
        valued.sort(key=getter, reverse=descending)
        empty = [it for it in items if getter(it) is None]
        ordered = valued + empty

        total = len(items)
        offset = (page - 1) * limit
        return {"total": total, "items": ordered[offset:offset + limit]}

    def get_detail(self, manager_id: str) -> dict | None:
        m = self.db.get(Manager, manager_id)
        if m is None:
            return None
        tenures = self.db.execute(
            select(ManagerTenure)
            .where(ManagerTenure.manager_id == manager_id)
            .order_by(ManagerTenure.tenure_days.desc())
        ).scalars().all()
        return {
            **self._to_dto(m),
            "career_days": m.career_days,
            "tenures": [
                {
                    "fund_code": t.fund_code,
                    "fund_name": t.fund_name,
                    "fund_type": t.fund_type,
                    "size_yi": t.size_yi,
                    "start_date": t.start_date.isoformat() if t.start_date else None,
                    "end_date": t.end_date.isoformat() if t.end_date else None,
                    "tenure_days": t.tenure_days,
                    "tenure_return": t.tenure_return,
                    "annual_return": t.annual_return,
                    "is_current": t.is_current,
                }
                for t in tenures
            ],
        }

    @staticmethod
    def _to_dto(m: Manager) -> dict:
        return {
            "manager_id": m.manager_id,
            "name": m.name,
            "company": m.company,
            "career_years": m.career_years,
            "current_scale_yi": m.current_scale_yi,
            "current_fund_count": m.current_fund_count,
            "managed_fund_count": m.managed_fund_count,
            "weighted_annual": m.tenure_weighted_annual,
            "longest_tenure_annual": m.longest_tenure_annual,
            "longest_tenure_years": m.longest_tenure_years,
            "max_drawdown": m.max_drawdown,
            "sharpe": m.sharpe,
            "calmar": m.calmar,
            "representative_fund": m.representative_fund,
        }

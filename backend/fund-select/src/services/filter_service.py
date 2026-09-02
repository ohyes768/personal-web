"""
筛选逻辑（核心）：四维度 + 排序

宇宙 = 库内 is_active 基金（配置名单已采集成功的）。
不按 category==bond 过滤：31 只里含混合/QDII，照常展示。

screen      — 通用筛选（债基 / 全用）
screen_stock — 仅股票型 + QDII（股票 tab 专用，fund_type LIKE 限定）
"""
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.db.models import Fund, FundFees, FundHoldingsBond, FundPerformance

# 排序白名单（防 SQL 注入）
SORT_COLUMNS = {
    "size_yi": Fund.size_yi,
    "age_years": Fund.age_years,
    "mgr_experience_years": Fund.mgr_experience_years,
    "dd_3y": FundPerformance.dd_3y,
    "ret_1y": FundPerformance.ret_1y,
    "ret_3y": FundPerformance.ret_3y,
    "ret_5y": FundPerformance.ret_5y,
    "fee_annual": FundFees.fee_mgmt,  # 年费排序：以管理费为主键近似（mgmt 占大头）
    "code": Fund.code,
}


def _fee_annual(fees: FundFees | None) -> Optional[float]:
    """年费 = 管理费 + 托管费 (+ 销售服务费)；任一缺失返回 None。"""
    if fees is None or fees.fee_mgmt is None or fees.fee_custody is None:
        return None
    return round(fees.fee_mgmt + fees.fee_custody + (fees.fee_service or 0), 4)


class FilterService:
    def __init__(self, db: Session):
        self.db = db

    def screen(
        self,
        min_age: Optional[float] = None,          # 成立年限 ≥ X（年）
        min_size_yi: Optional[float] = None,       # 规模 ≥ Y（亿）
        max_dd_3y: Optional[float] = None,         # 近 3 年最大回撤 ≤ Z%（注意库内为负数，比较绝对值）
        min_mgr_exp: Optional[float] = None,       # 经理从业年限 ≥ W（年）
        sort: str = "size_yi",
        order: str = "desc",
    ) -> dict:
        q = (
            select(Fund, FundPerformance, FundFees, FundHoldingsBond)
            .outerjoin(FundPerformance, Fund.code == FundPerformance.code)
            .outerjoin(FundFees, Fund.code == FundFees.code)
            .outerjoin(FundHoldingsBond, Fund.code == FundHoldingsBond.code)
            .where(Fund.is_active == True)  # noqa: E712
        )
        if min_age is not None:
            q = q.where(Fund.age_years >= min_age)
        if min_size_yi is not None:
            q = q.where(Fund.size_yi >= min_size_yi)
        if max_dd_3y is not None:
            # 库内 dd_3y 为负值（如 -4.47），用户输入阈值按绝对值（如 5）
            q = q.where(FundPerformance.dd_3y >= -abs(max_dd_3y))
        if min_mgr_exp is not None:
            q = q.where(Fund.mgr_experience_years >= min_mgr_exp)

        rows = self.db.execute(q).all()

        items = [self._to_dto(f, p, fee, hold) for f, p, fee, hold in rows]
        sort_key = sort if sort in SORT_COLUMNS else "size_yi"
        descending = order != "asc"

        # Python 侧排序：fee_annual 是计算字段；None 统一排最后
        key_map = {
            "size_yi": lambda it: it["size_yi"],
            "age_years": lambda it: it["age_years"],
            "mgr_experience_years": lambda it: it["mgr_experience_years"],
            "dd_3y": lambda it: None if it["dd_3y"] is None else abs(it["dd_3y"]),
            "ret_1y": lambda it: it["ret_1y"],
            "ret_3y": lambda it: it["ret_3y"],
            "ret_5y": lambda it: it["ret_5y"],
            "fee_annual": lambda it: it["fee_annual"],
            "code": lambda it: it["code"],
        }
        getter = key_map[sort_key]
        # dd_3y 用户视角：默认 desc = 回撤绝对值从大到小；asc = 小到大（最优在前）
        items.sort(
            key=lambda it: (getter(it) is None, getter(it) if getter(it) is not None else 0),
            reverse=descending,
        )
        return {"total": len(items), "items": items}

    def screen_stock(
        self,
        min_age: Optional[float] = None,
        min_size_yi: Optional[float] = None,
        max_dd_3y: Optional[float] = None,
        min_mgr_exp: Optional[float] = None,
        sort: str = "ret_5y",
        order: str = "desc",
    ) -> dict:
        """股票 tab 筛选：fund_type 限定股票型-* / QDII* / QDII。

        与 screen 主体逻辑同；仅追加 fund_type 谓词 + 默认 ret_5y desc（业绩优先）。
        """
        q = (
            select(Fund, FundPerformance, FundFees, FundHoldingsBond)
            .outerjoin(FundPerformance, Fund.code == FundPerformance.code)
            .outerjoin(FundFees, Fund.code == FundFees.code)
            .outerjoin(FundHoldingsBond, Fund.code == FundHoldingsBond.code)
            .where(Fund.is_active == True)  # noqa: E712
            .where(
                or_(
                    Fund.fund_type.like("股票型-%"),
                    Fund.fund_type.like("QDII%"),
                    Fund.fund_type == "QDII",
                )
            )
        )
        if min_age is not None:
            q = q.where(Fund.age_years >= min_age)
        if min_size_yi is not None:
            q = q.where(Fund.size_yi >= min_size_yi)
        if max_dd_3y is not None:
            q = q.where(FundPerformance.dd_3y >= -abs(max_dd_3y))
        if min_mgr_exp is not None:
            q = q.where(Fund.mgr_experience_years >= min_mgr_exp)

        rows = self.db.execute(q).all()
        items = [self._to_dto(f, p, fee, hold) for f, p, fee, hold in rows]
        sort_key = sort if sort in SORT_COLUMNS else "ret_5y"
        descending = order != "asc"

        key_map = {
            "size_yi": lambda it: it["size_yi"],
            "age_years": lambda it: it["age_years"],
            "mgr_experience_years": lambda it: it["mgr_experience_years"],
            "dd_3y": lambda it: None if it["dd_3y"] is None else abs(it["dd_3y"]),
            "ret_1y": lambda it: it["ret_1y"],
            "ret_3y": lambda it: it["ret_3y"],
            "ret_5y": lambda it: it["ret_5y"],
            "fee_annual": lambda it: it["fee_annual"],
            "code": lambda it: it["code"],
        }
        getter = key_map[sort_key]
        items.sort(
            key=lambda it: (getter(it) is None, getter(it) if getter(it) is not None else 0),
            reverse=descending,
        )
        return {"total": len(items), "items": items}

    @staticmethod
    def _to_dto(
        f: Fund, p: FundPerformance | None, fee: FundFees | None, hold: FundHoldingsBond | None
    ) -> dict:
        annual = _fee_annual(fee)
        return {
            "code": f.code,
            "name": f.name,
            "fund_type": f.fund_type,
            "size_yi": f.size_yi,
            "age_years": f.age_years,
            "dd_3y": p.dd_3y if p else None,
            "ret_1m": p.ret_1m if p else None,
            "ret_1y": p.ret_1y if p else None,
            "ret_3y": p.ret_3y if p else None,
            "ret_5y": p.ret_5y if p else None,
            "mgr_name": f.mgr_name,
            "mgr_company": f.mgr_company,
            "mgr_experience_years": f.mgr_experience_years,
            "rate_bond_pct": hold.rate_bond_pct if hold else None,
            "fee_mgmt": fee.fee_mgmt if fee else None,
            "fee_custody": fee.fee_custody if fee else None,
            "fee_service": fee.fee_service if fee else None,
            "fee_annual": annual,
            "updated_at": f.updated_at,
        }

    def get_detail(self, code: str) -> dict | None:
        """单只详情（fund + performance + fees + holdings）。"""
        row = self.db.execute(
            select(Fund, FundPerformance, FundFees, FundHoldingsBond)
            .outerjoin(FundPerformance, Fund.code == FundPerformance.code)
            .outerjoin(FundFees, Fund.code == FundFees.code)
            .outerjoin(FundHoldingsBond, Fund.code == FundHoldingsBond.code)
            .where(Fund.code == code)
        ).first()
        if row is None:
            return None
        f, p, fee, hold = row
        return {
            "code": f.code,
            "name": f.name,
            "fund_type": f.fund_type,
            "established_date": f.established_date,
            "age_years": f.age_years,
            "size_yi": f.size_yi,
            "mgr_name": f.mgr_name,
            "mgr_company": f.mgr_company,
            "mgr_days": f.mgr_days,
            "mgr_experience_years": f.mgr_experience_years,
            "is_active": f.is_active,
            "ret_1m": p.ret_1m if p else None,
            "ret_6m": p.ret_6m if p else None,
            "ret_1y": p.ret_1y if p else None,
            "ret_3y": p.ret_3y if p else None,
            "ret_5y": p.ret_5y if p else None,
            "dd_1y": p.dd_1y if p else None,
            "dd_3y": p.dd_3y if p else None,
            "dd_5y": p.dd_5y if p else None,
            "nav_latest": p.nav_latest if p else None,
            "nav_date": p.nav_date if p else None,
            "fees": {
                "fee_buy_small": fee.fee_buy_small if fee else None,
                "fee_redeem_lt7d": fee.fee_redeem_lt7d if fee else None,
                "fee_redeem_7d_1y": fee.fee_redeem_7d_1y if fee else None,
                "fee_redeem_ge1y": fee.fee_redeem_ge1y if fee else None,
                "fee_redeem_ge7d": fee.fee_redeem_ge7d if fee else None,
                "fee_mgmt": fee.fee_mgmt if fee else None,
                "fee_custody": fee.fee_custody if fee else None,
                "fee_service": fee.fee_service if fee else None,
            },
            "holdings": {
                "report_date": hold.report_date if hold else None,
                "rate_bond_pct": hold.rate_bond_pct if hold else None,
                "credit_bond_pct": hold.credit_bond_pct if hold else None,
                "convertible_pct": hold.convertible_pct if hold else None,
                "top5_concentration": hold.top5_concentration if hold else None,
                "top5_bonds": hold.top5_bonds if hold else None,
            } if hold else None,
        }

"""
筛选逻辑（核心）：四维度 + 排序

宇宙 = 各自 yaml 名单 ∩ 库内 is_active。
screen      — 债基 tab，读 funds.yaml
screen_stock — 股票 tab，读 funds_stock.yaml

fund_type 只当表格展示字段，不做成员判定。
yaml 手工名单已经分好债基/股票宇宙，不需要 LIKE 股票型/QDII/混合型。
以后扫全市场时再按 fund_type 收口（本模块尚未实现）。
用户可选 exclude_qdii：丢掉 fund_type 以 QDII 开头或「互认基金」的记录（两 tab 都支持）。
"""
from typing import Optional

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from src.data.fund_universe import resolve_universe_codes
from src.db.models import Fund, FundFees, FundHoldingsBond, FundPerformance, FundRiskMetrics

# 排序白名单（防 SQL 注入）
SORT_COLUMNS = {
    "size_yi": Fund.size_yi,
    "age_years": Fund.age_years,
    "mgr_experience_years": Fund.mgr_experience_years,
    "dd_3y": FundPerformance.dd_3y,
    "ret_1y": FundPerformance.ret_1y,
    "ret_3y": FundPerformance.ret_3y,
    "ret_5y": FundPerformance.ret_5y,
    "sharpe": FundRiskMetrics.sharpe,
    "ir": FundRiskMetrics.ir,
    "alpha": FundRiskMetrics.alpha,
    "gamma": FundRiskMetrics.gamma,
    "alpha_ir": FundRiskMetrics.alpha_ir,
    "excess_3y": FundRiskMetrics.excess_3y,
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
        exclude_qdii: bool = False,
        universe_codes: list[str] | None = None,
    ) -> dict:
        return self._screen(
            "bond", min_age, min_size_yi, max_dd_3y, min_mgr_exp,
            sort, order, universe_codes, exclude_qdii,
        )

    def screen_stock(
        self,
        min_age: Optional[float] = None,
        min_size_yi: Optional[float] = None,
        max_dd_3y: Optional[float] = None,
        min_mgr_exp: Optional[float] = None,
        min_sharpe: Optional[float] = None,        # 夏普 ≥ X（近 3 年；NULL 指标被排除）
        sort: str = "ret_5y",
        order: str = "desc",
        exclude_qdii: bool = False,
        universe_codes: list[str] | None = None,
    ) -> dict:
        """股票 tab 筛选：成员 = funds_stock.yaml ∩ is_active（不看 fund_type）。"""
        return self._screen(
            "stock", min_age, min_size_yi, max_dd_3y, min_mgr_exp,
            sort, order, universe_codes, exclude_qdii, min_sharpe,
        )

    def universe_stats(
        self,
        kind: str,
        universe_codes: list[str] | None = None,
    ) -> dict:
        """按宇宙统计活跃基金及关联表覆盖。不含 last_refresh_at。"""
        codes = resolve_universe_codes(kind, universe_codes)
        empty = {"total": 0, "with_performance": 0, "with_fees": 0, "with_holdings": 0}
        if not codes:
            return empty
        active = set(
            self.db.execute(
                select(Fund.code).where(
                    Fund.is_active == True,  # noqa: E712
                    Fund.code.in_(codes),
                )
            ).scalars().all()
        )
        if not active:
            return empty
        with_perf = self.db.execute(
            select(func.count()).select_from(FundPerformance).where(
                FundPerformance.code.in_(active)
            )
        ).scalar() or 0
        with_fees = self.db.execute(
            select(func.count()).select_from(FundFees).where(FundFees.code.in_(active))
        ).scalar() or 0
        with_hold = self.db.execute(
            select(func.count()).select_from(FundHoldingsBond).where(
                FundHoldingsBond.code.in_(active)
            )
        ).scalar() or 0
        return {
            "total": len(active),
            "with_performance": with_perf,
            "with_fees": with_fees,
            "with_holdings": with_hold,
        }

    def _screen(
        self,
        kind: str,
        min_age: Optional[float],
        min_size_yi: Optional[float],
        max_dd_3y: Optional[float],
        min_mgr_exp: Optional[float],
        sort: str,
        order: str,
        universe_codes: list[str] | None,
        exclude_qdii: bool = False,
        min_sharpe: Optional[float] = None,
    ) -> dict:
        codes = resolve_universe_codes(kind, universe_codes)
        if not codes:
            return {"total": 0, "items": []}
        q = (
            select(Fund, FundPerformance, FundFees, FundHoldingsBond, FundRiskMetrics)
            .outerjoin(FundPerformance, Fund.code == FundPerformance.code)
            .outerjoin(FundFees, Fund.code == FundFees.code)
            .outerjoin(FundHoldingsBond, Fund.code == FundHoldingsBond.code)
            .outerjoin(FundRiskMetrics, Fund.code == FundRiskMetrics.code)
            .where(Fund.is_active == True)  # noqa: E712
            .where(Fund.code.in_(codes))
        )
        if exclude_qdii:
            # fund_type 为 NULL 的保留；只丢掉 QDII* 与「互认基金」
            q = q.where(
                or_(
                    Fund.fund_type.is_(None),
                    and_(
                        not_(Fund.fund_type.like("QDII%")),
                        Fund.fund_type != "互认基金",
                    ),
                )
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
        if min_sharpe is not None:
            # sharpe 为 NULL（无风险指标）的基金一并排除，与 dd_3y 筛选惯例一致
            q = q.where(FundRiskMetrics.sharpe >= min_sharpe)

        rows = self.db.execute(q).all()
        items = [self._to_dto(f, p, fee, hold, risk) for f, p, fee, hold, risk in rows]
        default_sort = "ret_5y" if kind == "stock" else "size_yi"
        sort_key = sort if sort in SORT_COLUMNS else default_sort
        descending = order != "asc"

        key_map = {
            "size_yi": lambda it: it["size_yi"],
            "age_years": lambda it: it["age_years"],
            "mgr_experience_years": lambda it: it["mgr_experience_years"],
            "dd_3y": lambda it: None if it["dd_3y"] is None else abs(it["dd_3y"]),
            "ret_1y": lambda it: it["ret_1y"],
            "ret_3y": lambda it: it["ret_3y"],
            "ret_5y": lambda it: it["ret_5y"],
            "sharpe": lambda it: it["sharpe"],
            "ir": lambda it: it["ir"],
            "alpha": lambda it: it["alpha"],
            "gamma": lambda it: it["gamma"],
            "alpha_ir": lambda it: it["alpha_ir"],
            "excess_3y": lambda it: it["excess_3y"],
            "fee_annual": lambda it: it["fee_annual"],
            "code": lambda it: it["code"],
        }
        getter = key_map[sort_key]
        # None 值永远排尾部（asc/desc 皆是）：先排非 None，再追加 None
        valued = [it for it in items if getter(it) is not None]
        valued.sort(key=getter, reverse=descending)
        empty = [it for it in items if getter(it) is None]
        return {"total": len(items), "items": valued + empty}

    @staticmethod
    def _to_dto(
        f: Fund, p: FundPerformance | None, fee: FundFees | None, hold: FundHoldingsBond | None,
        risk: FundRiskMetrics | None = None,
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
            "sharpe": risk.sharpe if risk else None,
            "ir": risk.ir if risk else None,
            "alpha": risk.alpha if risk else None,
            "gamma": risk.gamma if risk else None,
            "alpha_ir": risk.alpha_ir if risk else None,
            "excess_3y": risk.excess_3y if risk else None,
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

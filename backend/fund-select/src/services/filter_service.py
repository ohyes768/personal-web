"""
筛选逻辑（核心）：四维度 + 排序

四种 tab：
- screen          — 债基 tab（funds.yaml 名单）
- screen_stock    — 股票 tab（funds_stock.yaml 名单）
- screen_discovery_bond  — 债基·市场 tab（akshare market_subtype 子类精确 IN）
- screen_discovery_stock — 股基·市场 tab

来源合并（11-15-source-segmented，两 tab + 来源分段控件）：
- screen / screen_stock 新增 source 参数（curated|market|all，默认 curated）：
  curated = yaml 名单；market = akshare 子类圈定；all = 两者并集。
  行上带 in_curated 标记（code ∈ yaml 名单），供「全部」态徽章展示。
- screen_discovery_* 保留为 market 薄包装（旧路由兼容，不再从导航进入）。

fund_type 只当表格展示字段，不做成员判定。
yaml 手工名单已经分好债基/股票宇宙，不需要 LIKE 股票型/QDII/混合型。
市场 tab 用 akshare 子类（market_subtype 字段）+ market_type tab 分类作为成员判定。
以后扫全市场时再按 fund_type 收口（本模块尚未实现）。
用户可选 exclude_qdii：丢掉 fund_type 以 QDII 开头或「互认基金」的记录（四 tab 都支持）。
"""
from typing import Optional

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from src.data.fund_universe import resolve_universe_codes
from src.db.models import (
    Fund,
    FundAchievementRank,
    FundFees,
    FundHoldingsBond,
    FundPerformance,
    FundRiskMetrics,
    MarketFundRank,
)
from src.data.market_subtype_map import (
    DISCOVERY_BOND_SUBTYPES,
    DISCOVERY_STOCK_SUBTYPES,
)
from src.utils.rank import parse_peer_rank

# 各 tab 的默认市场 universe（akshare 子类精确枚举）
DEFAULT_DISCOVERY_UNIVERSE: dict[str, list[str]] = {
    "discovery-bond": list(DISCOVERY_BOND_SUBTYPES),
    "discovery-stock": list(DISCOVERY_STOCK_SUBTYPES),
}

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


def _parse_peer_rank(value: str | None) -> dict | None:
    """'1694/5606' → {'pct': 30.2, 'total': 5606, 'rank': 1694}；格式异常/缺分母 → None。

    用于股票 tab 同类排名显示；债基 tab 永远返回 None（无入库数据）。
    实现已移至 src/utils/rank.py（经理明细的历任基金行共用）。
    """
    return parse_peer_rank(value)


# stock tab 主表 4 个排名口径：(period_kind, period) → DTO 键
RANK_PERIODS: list[tuple[str, str, str]] = [
    ("年度业绩", "今年以来", "rank_ytd"),
    ("阶段业绩", "近1年",    "rank_1y"),
    ("阶段业绩", "近3年",    "rank_3y"),
    ("阶段业绩", "近5年",    "rank_5y"),
]


def _predicate_field(row, key: str):
    """行级谓词取字段：dict（capture 冻结数据）与 ORM 行/命名空间均可。"""
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def entry_predicate(
    *,
    min_age: Optional[float] = None,
    min_size_yi: Optional[float] = None,
    max_dd_3y: Optional[float] = None,
    min_mgr_exp: Optional[float] = None,
    min_sharpe: Optional[float] = None,
    exclude_qdii: bool = False,
    min_ir: Optional[float] = None,
    min_sample_days: Optional[float] = None,
    max_peer_pct: Optional[float] = None,
    min_yearly_years: Optional[float] = None,
):
    """入选谓词（行级）：实时 SQL 筛选（_screen 的 where 链）与夏普榜单 capture
    冻结数据共用的同一份阈值语义。

    返回 fn(row) -> bool。row 需提供 age_years / size_yi / dd_3y /
    mgr_experience_years / sharpe / market_subtype（dict 或带属性对象均可）。

    与 SQL where 的语义对齐（由等价性测试锁定，勿单改一边）：
    - NULL 处理：SQL col >= X 对 NULL 行为 falsy → 任一所选维度为 None 即不命中
    - 阈值含等号：SQL >= ↔ Python >=（如 dd_3y=-10 过 max_dd_3y=10、
      sharpe=0.8 过 min_sharpe=0.8）
    - dd_3y 库内为负值，按绝对值比较：SQL dd_3y >= -abs(X) ↔ Python v < -abs(X) 淘汰
    - exclude_qdii：market_subtype 为 None/空串保留；丢 QDII*（LIKE 'QDII%'）与
      「互认基金」——字段是 market_subtype（精确 akshare 子类），不是 fund_type
    - 市场子类成员判定（market_types IN 精确 subtype）不在此谓词内：与 _screen
      一致，成员判定是 universe 层（SQL .in_），调用方自行组合

    v2 新增三道门（11-13-sharpe-board-v2-rules）：三个参数默认 None 时行为与
    v1 逐字节一致，供 v1 profile 继续沿用；v2 profile 才传值。
    - min_ir：信息比率 ≥ X；NULL 不命中（QDII 无基准等场景）
    - min_sample_days：样本交易日数 ≥ X；NULL 不命中
    - max_peer_pct：同类分位 ≤ X%（即前 X%），含等号；无数据/格式异常 →
      freeze_peer_rows 阶段已丢弃该 code，此处 peer_pct 为 None 即不命中。
      同类排名的 90 天陈旧过滤在冻结阶段完成，谓词保持纯函数（不依赖 today()）。

    v3 新增年度同类排名门槛（min_yearly_years，默认 None = 不判断）：
    - 语义：最近 N 个完整年度中，同类分位 ≤ top_pct 的年数 ≥ min_yearly_years
    - 谓词只读冻结好的 qualified_years（阈值与达标年数在 freeze_yearly_peer_rows
      里按本轮 profile 快照算好），保持纯函数；无证据（None）不命中
    - 与 max_peer_pct 不可混用：后者是滚动口径「单个分位 ≤ X」，语义不同
    """
    def predicate(row) -> bool:
        if exclude_qdii:
            sub = _predicate_field(row, "market_subtype")
            if sub and (sub.startswith("QDII") or sub == "互认基金"):
                return False
        if min_age is not None:
            v = _predicate_field(row, "age_years")
            if v is None or v < min_age:
                return False
        if min_size_yi is not None:
            v = _predicate_field(row, "size_yi")
            if v is None or v < min_size_yi:
                return False
        if max_dd_3y is not None:
            v = _predicate_field(row, "dd_3y")
            # 库内 dd_3y 为负值（如 -4.47），阈值按绝对值（SQL: dd_3y >= -abs(X)）
            if v is None or v < -abs(max_dd_3y):
                return False
        if min_mgr_exp is not None:
            # 用 *_max（共管取最长）：有资深经理在管即达标。
            # 旧口径取 min 会把「22 年老将 + 3 年新人」判成 3 年而误杀。
            # 兼容：max 列未回填（历史行为 NULL）时回退到 mgr_experience_years。
            v = _predicate_field(row, "mgr_experience_years_max")
            if v is None:
                v = _predicate_field(row, "mgr_experience_years")
            if v is None or v < min_mgr_exp:
                return False
        if min_sharpe is not None:
            v = _predicate_field(row, "sharpe")
            # sharpe 为 NULL（无风险指标）一并排除，与 SQL 筛选惯例一致
            if v is None or v < min_sharpe:
                return False
        # ---- v2 三道新门槛（参数 None 时整段跳过，v1 行为不变）----
        if min_ir is not None:
            v = _predicate_field(row, "ir")
            if v is None or v < min_ir:
                return False
        if min_sample_days is not None:
            v = _predicate_field(row, "sample_days")
            if v is None or v < min_sample_days:
                return False
        if max_peer_pct is not None:
            v = _predicate_field(row, "peer_pct")
            # 前 X%：rank/total*100 <= X（含等号）
            if v is None or v > max_peer_pct:
                return False
        # ---- v3 年度同类排名门槛（参数 None 时整段跳过）----
        if min_yearly_years is not None:
            # qualified_years 由 freeze_yearly_peer_rows 冻结时算好
            # （阈值也在冻结时快照），谓词只做数值比较，不重复算分位
            v = _predicate_field(row, "qualified_years")
            if v is None or v < min_yearly_years:
                return False
        return True

    return predicate


class FilterService:
    def __init__(self, db: Session):
        self.db = db

    # 来源分段（11-15-source-segmented）：curated=三分法 yaml 名单，market=akshare 子类，
    # all=并集。行上带 in_curated 标记供「全部」态徽章展示。
    SOURCE_VALUES = ("all", "curated", "market")

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
        page: int = 1,
        limit: int = 50,
        source: str = "curated",
    ) -> dict:
        """债基筛选：source=curated（yaml 名单，默认=旧债基 tab）/ market / all（并集）。"""
        return self._screen_sourced(
            curated_kind="bond", market_kind="discovery-bond", source=source,
            min_age=min_age, min_size_yi=min_size_yi, max_dd_3y=max_dd_3y,
            min_mgr_exp=min_mgr_exp, sort=sort, order=order,
            universe_codes=universe_codes, exclude_qdii=exclude_qdii,
            page=page, limit=limit,
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
        page: int = 1,
        limit: int = 50,
        source: str = "curated",
    ) -> dict:
        """股基筛选：source=curated（funds_stock.yaml，默认=旧股票 tab）/ market / all。"""
        return self._screen_sourced(
            curated_kind="stock", market_kind="discovery-stock", source=source,
            min_age=min_age, min_size_yi=min_size_yi, max_dd_3y=max_dd_3y,
            min_mgr_exp=min_mgr_exp, sort=sort, order=order,
            universe_codes=universe_codes, exclude_qdii=exclude_qdii,
            min_sharpe=min_sharpe, page=page, limit=limit,
        )

    def _screen_sourced(
        self,
        *,
        curated_kind: str,
        market_kind: str,
        source: str,
        min_age: Optional[float] = None,
        min_size_yi: Optional[float] = None,
        max_dd_3y: Optional[float] = None,
        min_mgr_exp: Optional[float] = None,
        min_sharpe: Optional[float] = None,
        sort: str = "size_yi",
        order: str = "desc",
        exclude_qdii: bool = False,
        universe_codes: list[str] | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        """统一入口：按 source 决定成员判定，_screen 完成筛选与排序。

        - curated：yaml 名单（resolve_universe_codes），in_curated 恒 True
        - market：akshare 子类圈定（DEFAULT_DISCOVERY_UNIVERSE），in_curated 按
          code 是否 ∈ yaml 名单逐行算（市场子类 ∩ 名单有交集）
        - all：两个 universe 的 code 并集（SQL IN，不取回再过滤）
        """
        if source not in self.SOURCE_VALUES:
            raise ValueError(f"unknown source: {source}")
        curated_codes = resolve_universe_codes(curated_kind, universe_codes)

        if source == "curated":
            if not curated_codes:
                return {"total": 0, "items": []}
            result = self._screen(
                curated_kind, min_age, min_size_yi, max_dd_3y, min_mgr_exp,
                sort, order, curated_codes, exclude_qdii, min_sharpe,
                page=page, limit=limit,
            )
        else:
            types = DEFAULT_DISCOVERY_UNIVERSE[market_kind]
            if source == "market":
                if not types:
                    return {"total": 0, "items": []}
                result = self._screen(
                    market_kind, min_age, min_size_yi, max_dd_3y, min_mgr_exp,
                    sort, order, None, exclude_qdii, min_sharpe, types,
                    page=page, limit=limit,
                )
            else:  # all：yaml ∪ 子类（并集 code IN，一次查询）
                if not types and not curated_codes:
                    return {"total": 0, "items": []}
                union_codes = list(dict.fromkeys(curated_codes))  # 去重保序
                if types:
                    union_extra = self.db.execute(
                        select(Fund.code).where(
                            Fund.is_active == True,  # noqa: E712
                            Fund.market_subtype.in_(types),
                        )
                    ).scalars().all()
                    union_codes = list(dict.fromkeys(union_codes + union_extra))
                if not union_codes:
                    return {"total": 0, "items": []}
                result = self._screen(
                    "all-codes", min_age, min_size_yi, max_dd_3y, min_mgr_exp,
                    sort, order, union_codes, exclude_qdii, min_sharpe,
                    page=page, limit=limit,
                )

        # in_curated 标记：curated 态恒 True；market/all 态按名单成员逐行算
        curated_set = set(curated_codes)
        for it in result.get("items", []):
            it["in_curated"] = it["code"] in curated_set
        result["source"] = source
        return result


    def screen_discovery_bond(
        self,
        min_age: Optional[float] = None,
        min_size_yi: Optional[float] = None,
        max_dd_3y: Optional[float] = None,
        min_mgr_exp: Optional[float] = None,
        min_sharpe: Optional[float] = None,
        min_ret_1y: Optional[float] = None,
        min_ret_3y: Optional[float] = None,
        max_nav_stale_days: Optional[int] = None,
        sort: str = "size_yi",
        order: str = "desc",
        exclude_qdii: bool = False,
        market_types: list[str] | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        """债基·市场 tab 筛选：成员 = market_subtype ∈ default['discovery-bond'] ∩ is_active。"""
        types = market_types if market_types is not None else DEFAULT_DISCOVERY_UNIVERSE["discovery-bond"]
        return self._screen(
            "discovery-bond", min_age, min_size_yi, max_dd_3y, min_mgr_exp,
            sort, order, None, exclude_qdii, min_sharpe, types,
            min_ret_1y=min_ret_1y, min_ret_3y=min_ret_3y,
            max_nav_stale_days=max_nav_stale_days,
            page=page, limit=limit,
        )

    def screen_discovery_stock(
        self,
        min_age: Optional[float] = None,
        min_size_yi: Optional[float] = None,
        max_dd_3y: Optional[float] = None,
        min_mgr_exp: Optional[float] = None,
        min_sharpe: Optional[float] = None,
        min_ret_1y: Optional[float] = None,
        min_ret_3y: Optional[float] = None,
        max_nav_stale_days: Optional[int] = None,
        sort: str = "ret_5y",
        order: str = "desc",
        exclude_qdii: bool = False,
        market_types: list[str] | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        """股基·市场 tab 筛选：成员 = market_subtype ∈ default['discovery-stock'] ∩ is_active。"""
        types = market_types if market_types is not None else DEFAULT_DISCOVERY_UNIVERSE["discovery-stock"]
        return self._screen(
            "discovery-stock", min_age, min_size_yi, max_dd_3y, min_mgr_exp,
            sort, order, None, exclude_qdii, min_sharpe, types,
            min_ret_1y=min_ret_1y, min_ret_3y=min_ret_3y,
            max_nav_stale_days=max_nav_stale_days,
            page=page, limit=limit,
        )

    def universe_stats(
        self,
        kind: str,
        universe_codes: list[str] | None = None,
        market_types: list[str] | None = None,
    ) -> dict:
        """按宇宙统计活跃基金及关联表覆盖。不含 last_refresh_at。

        kind:
          - 'bond' / 'stock'：走 yaml 名单（resolve_universe_codes）
          - 'discovery-bond' / 'discovery-stock'：走 market_type（DEFAULT_DISCOVERY_UNIVERSE）
        """
        empty = {"total": 0, "with_performance": 0, "with_fees": 0, "with_holdings": 0}

        if kind in ("bond", "stock"):
            codes = resolve_universe_codes(kind, universe_codes)
            if not codes:
                return empty
            active_q = (
                select(Fund.code)
                .where(Fund.is_active == True, Fund.code.in_(codes))  # noqa: E712
            )
        elif kind in ("discovery-bond", "discovery-stock"):
            types = market_types if market_types is not None else DEFAULT_DISCOVERY_UNIVERSE[kind]
            if not types:
                return empty
            active_q = (
                select(Fund.code)
                .where(Fund.is_active == True, Fund.market_subtype.in_(types))  # noqa: E712
            )
        else:
            raise ValueError(f"unknown universe kind: {kind}")

        active = set(self.db.execute(active_q).scalars().all())
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

    def universe_stats_sourced(
        self,
        curated_kind: str,
        market_kind: str,
        source: str = "curated",
    ) -> dict:
        """按来源分段统计（与 _screen_sourced 的成员判定一致）。

        - curated：yaml 名单
        - market：akshare 子类圈定
        - all：yaml ∪ 子类（并集）
        """
        empty = {"total": 0, "with_performance": 0, "with_fees": 0, "with_holdings": 0}
        if source == "curated":
            return self.universe_stats(curated_kind)
        if source == "market":
            return self.universe_stats(market_kind)
        if source == "all":
            curated_codes = set(resolve_universe_codes(curated_kind))
            types = DEFAULT_DISCOVERY_UNIVERSE[market_kind]
            active_q = select(Fund.code).where(Fund.is_active == True)  # noqa: E712
            if types:
                active_q = active_q.where(Fund.market_subtype.in_(types))
            active = set(self.db.execute(active_q).scalars().all())
            # 名单基金不一定在子类里（或子类字段为空）——并集要显式加回来
            curated_active = self.db.execute(
                select(Fund.code).where(
                    Fund.is_active == True,  # noqa: E712
                    Fund.code.in_(curated_codes),
                )
            ).scalars().all() if curated_codes else []
            active |= set(curated_active)
            if not active:
                return empty
            return self._stats_for_codes(active)
        raise ValueError(f"unknown source: {source}")

    def _stats_for_codes(self, codes: set[str]) -> dict:
        """对给定 code 集合统计活跃数与关联表覆盖（universe_stats 的并集分支）。"""
        empty = {"total": 0, "with_performance": 0, "with_fees": 0, "with_holdings": 0}
        if not codes:
            return empty
        with_perf = self.db.execute(
            select(func.count()).select_from(FundPerformance).where(
                FundPerformance.code.in_(codes)
            )
        ).scalar() or 0
        with_fees = self.db.execute(
            select(func.count()).select_from(FundFees).where(FundFees.code.in_(codes))
        ).scalar() or 0
        with_hold = self.db.execute(
            select(func.count()).select_from(FundHoldingsBond).where(
                FundHoldingsBond.code.in_(codes)
            )
        ).scalar() or 0
        return {
            "total": len(codes),
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
        market_types: list[str] | None = None,
        min_ret_1y: Optional[float] = None,
        min_ret_3y: Optional[float] = None,
        max_nav_stale_days: Optional[int] = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        # 成员判定：bond/stock 走 yaml；discovery-* 走 market_subtype；
        # all-codes 直接用调用方给定的 code 并集（_screen_sourced 的 all 态）
        if kind in ("bond", "stock", "all-codes"):
            codes = resolve_universe_codes(kind, universe_codes) if kind != "all-codes" else (universe_codes or [])
            if not codes:
                return {"total": 0, "items": []}
            q = (
                select(Fund, FundPerformance, FundFees, FundHoldingsBond,
                       FundRiskMetrics, MarketFundRank)
                .outerjoin(FundPerformance, Fund.code == FundPerformance.code)
                .outerjoin(FundFees, Fund.code == FundFees.code)
                .outerjoin(FundHoldingsBond, Fund.code == FundHoldingsBond.code)
                .outerjoin(FundRiskMetrics, Fund.code == FundRiskMetrics.code)
                .outerjoin(MarketFundRank, Fund.code == MarketFundRank.code)
                .where(Fund.is_active == True)  # noqa: E712
                .where(Fund.code.in_(codes))
            )
        elif kind in ("discovery-bond", "discovery-stock"):
            types = market_types if market_types is not None else DEFAULT_DISCOVERY_UNIVERSE[kind]
            if not types:
                return {"total": 0, "items": []}
            q = (
                select(Fund, FundPerformance, FundFees, FundHoldingsBond,
                       FundRiskMetrics, MarketFundRank)
                .outerjoin(FundPerformance, Fund.code == FundPerformance.code)
                .outerjoin(FundFees, Fund.code == FundFees.code)
                .outerjoin(FundHoldingsBond, Fund.code == FundHoldingsBond.code)
                .outerjoin(FundRiskMetrics, Fund.code == FundRiskMetrics.code)
                .outerjoin(MarketFundRank, Fund.code == MarketFundRank.code)
                .where(Fund.is_active == True)  # noqa: E712
                .where(Fund.market_subtype.in_(types))
            )
        else:
            raise ValueError(f"unknown screen kind: {kind}")

        if exclude_qdii:
            # market_subtype 为 NULL/空 的保留；只丢掉 QDII* 与「互认基金」
            # （funds.fund_type 字段从 fetch_market_universe 没填过，全为空；
            #  用 market_subtype 才是准的；fund_type 是「债基/股票」tab 老分类预留字段）
            q = q.where(
                or_(
                    Fund.market_subtype.is_(None),
                    Fund.market_subtype == "",
                    and_(
                        not_(Fund.market_subtype.like("QDII%")),
                        Fund.market_subtype != "互认基金",
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
            # 共管取最长（*_max）；未回填时回退老字段，语义见 entry_predicate
            q = q.where(
                func.coalesce(
                    Fund.mgr_experience_years_max,
                    Fund.mgr_experience_years,
                ) >= min_mgr_exp
            )
        if min_sharpe is not None:
            # sharpe 为 NULL（无风险指标）的基金一并排除，与 dd_3y 筛选惯例一致
            q = q.where(FundRiskMetrics.sharpe >= min_sharpe)
        if min_ret_1y is not None:
            # 隐式要求成立 ≥ 1 年（ret_1y IS NULL = akshare 没给，近似 < 1 年）
            q = q.where(MarketFundRank.ret_1y >= min_ret_1y)
        if min_ret_3y is not None:
            # 隐式要求成立 ≥ 3 年
            q = q.where(MarketFundRank.ret_3y >= min_ret_3y)
        if max_nav_stale_days is not None:
            # 净值日距今 ≤ N 天（NULL 也算通过）
            from datetime import date as _date, timedelta as _td
            cutoff = _date.today() - _td(days=max_nav_stale_days)
            from sqlalchemy import or_ as _or
            q = q.where(_or(MarketFundRank.nav_date.is_(None),
                            MarketFundRank.nav_date >= cutoff))

        rows = self.db.execute(q).all()
        # 一次性取 4 个目标周期排名（30 只名单下 ≤120 行）；dict 查找避免 ORM subquery 复杂度
        ach_map: dict[str, dict[tuple[str, str], str | None]] = {}
        if rows:
            codes = [f.code for f, *_ in rows]
            pairs = [(pk, pp) for pk, pp, _ in RANK_PERIODS]
            ach_rows = self.db.execute(
                select(
                    FundAchievementRank.code,
                    FundAchievementRank.period_kind,
                    FundAchievementRank.period,
                    FundAchievementRank.peer_rank,
                )
                .where(FundAchievementRank.code.in_(codes))
                .where(
                    or_(*[
                        and_(
                            FundAchievementRank.period_kind == pk,
                            FundAchievementRank.period == pp,
                        )
                        for pk, pp in pairs
                    ])
                )
            ).all()
            for r in ach_rows:
                ach_map.setdefault(r.code, {})[(r.period_kind, r.period)] = r.peer_rank

        items = [
            self._to_dto(f, p, fee, hold, risk, market_rank, ach_map.get(f.code))
            for f, p, fee, hold, risk, market_rank in rows
        ]
        default_sort = "ret_5y" if kind in ("stock", "discovery-stock") else "size_yi"
        sort_key = sort if sort in SORT_COLUMNS else default_sort
        descending = order != "asc"

        key_map = {
            "size_yi": lambda it: it["size_yi"],
            "age_years": lambda it: it["age_years"],
            "mgr_experience_years": lambda it: (
                it["mgr_experience_years_max"]
                if it.get("mgr_experience_years_max") is not None
                else it["mgr_experience_years"]
            ),
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
        # 分页切片：total 是筛后总数（与 page/limit 无关）；items 切片
        total = len(items)
        ordered = valued + empty
        offset = (page - 1) * limit
        items_page = ordered[offset:offset + limit]
        return {"total": total, "items": items_page}

    @staticmethod
    def _to_dto(
        f: Fund, p: FundPerformance | None, fee: FundFees | None, hold: FundHoldingsBond | None,
        risk: FundRiskMetrics | None = None,
        market_rank: MarketFundRank | None = None,
        ach_for_code: dict[tuple[str, str], str | None] | None = None,
    ) -> dict:
        annual = _fee_annual(fee)
        # 4 个排名周期：缺失/异常统一为 None；债基 tab ach_for_code 为空 dict → 全部 None
        ranks = {
            key: _parse_peer_rank((ach_for_code or {}).get((pk, pp)))
            for pk, pp, key in RANK_PERIODS
        }
        return {
            "code": f.code,
            "name": f.name,
            "fund_type": f.fund_type,
            "market_subtype": f.market_subtype,  # akshare 精确子类（前端类型列展示用）
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
            "mgr_experience_years_max": f.mgr_experience_years_max,
            "rate_bond_pct": hold.rate_bond_pct if hold else None,
            "fee_mgmt": fee.fee_mgmt if fee else None,
            "fee_custody": fee.fee_custody if fee else None,
            "fee_service": fee.fee_service if fee else None,
            "fee_annual": annual,
            "updated_at": f.updated_at,
            # market_fund_rank 字段（L1 业绩）
            "mr_nav_latest": market_rank.nav_latest if market_rank else None,
            "mr_nav_date": market_rank.nav_date.isoformat() if market_rank and market_rank.nav_date else None,
            "mr_ret_1w": market_rank.ret_1w if market_rank else None,
            "mr_ret_1m": market_rank.ret_1m if market_rank else None,
            "mr_ret_3m": market_rank.ret_3m if market_rank else None,
            "mr_ret_6m": market_rank.ret_6m if market_rank else None,
            "mr_ret_1y": market_rank.ret_1y if market_rank else None,
            "mr_ret_2y": market_rank.ret_2y if market_rank else None,
            "mr_ret_3y": market_rank.ret_3y if market_rank else None,
            "mr_ret_ytd": market_rank.ret_ytd if market_rank else None,
            "mr_ret_all": market_rank.ret_all if market_rank else None,
            **ranks,
        }

    def get_detail(self, code: str) -> dict | None:
        """单只详情（fund + performance + fees + holdings + risk）。"""
        row = self.db.execute(
            select(Fund, FundPerformance, FundFees, FundHoldingsBond, FundRiskMetrics)
            .outerjoin(FundPerformance, Fund.code == FundPerformance.code)
            .outerjoin(FundFees, Fund.code == FundFees.code)
            .outerjoin(FundHoldingsBond, Fund.code == FundHoldingsBond.code)
            .outerjoin(FundRiskMetrics, Fund.code == FundRiskMetrics.code)
            .where(Fund.code == code)
        ).first()
        if row is None:
            return None
        f, p, fee, hold, risk = row
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
            "mgr_experience_years_max": f.mgr_experience_years_max,
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
            "sharpe": risk.sharpe if risk else None,
            "ir": risk.ir if risk else None,
            "alpha": risk.alpha if risk else None,
            "gamma": risk.gamma if risk else None,
            "alpha_ir": risk.alpha_ir if risk else None,
            "excess_3y": risk.excess_3y if risk else None,
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

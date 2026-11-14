"""经理筛选服务（/api/funds/managers，任务 11-10-fund-manager-evaluation）。

以 managers 表为主体聚合排序；与基金 /screen 完全独立，不改其语义。
分页契约与 FilterService 对齐：total = 筛后总数，items = 当页，None 值排尾部。

派生指标（11-12，调研任务沉淀，全部由 manager_tenures 聚合、不新增采集）：
- tenure_win_rate 任期胜率：tenure_return>0 的任期占比（剔除无回报段）。
  库内中位数 ~55%，≥2/3 即显著优于平均。
- solo_ratio 独管比例：当前在管基金中仅自己一位经理的占比；
  共管多 → 贡献难归因（挂名风险）。
- rep_divergence 代表作背离：longest_tenure_annual - tenure_weighted_annual。
  >15pp 说明业绩集中在单只代表作（幸存者偏差），只做展示不进筛选。
- current_weighted_annual 在管年化：仅 is_current 段的时长加权年化。
  managers.tenure_weighted_annual 含离任段（职业生涯口径）；在管口径回答
  「他现在管的这几只表现如何」。两者背离本身有信息量：含离任高、在管低
  = 状态下滑或新管不久。同样只展示+排序，不进筛选。
- board_on_current 在管在榜数：当前在管基金出现在夏普周观测里的数量
  （历史累计口径：上过任何一周的榜即算；列表行汇总徽章用）。
- get_detail 的任期行带 affiliation 归属（tab 名单/在榜周数），前端渲染
  可点徽章并跳转对应 tab（双向闭环的第 1 层）。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from src.db.models import (
    Fund,
    FundAchievementRank,
    FundPerformance,
    Manager,
    ManagerTenure,
    MarketFundRank,
    SharpeBoardObservation,
    SharpeBoardWeek,
)
from src.data.fund_universe import resolve_universe_codes
from src.services.manager_metrics import is_active_equity
from src.utils.rank import parse_peer_rank


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
    "tenure_win_rate": (None, "desc"),   # 派生列，仅用于取默认方向
    "current_weighted_annual": (None, "desc"),  # 同上（在管口径年化）
    "solo_ratio": (None, "desc"),        # 同上
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
        min_win_rate: Optional[float] = None,      # 任期胜率 ≥ %（0-100）
        min_solo_ratio: Optional[float] = None,    # 独管比例 ≥ %（0-100）
        max_fund_count: Optional[int] = None,      # 在管基金数 ≤ N（精力分散门槛，中基协上限 10）
        keyword: Optional[str] = None,             # 姓名/公司模糊
        sort: str = "current_weighted_annual",     # 默认「在管年化」：当下状态口径
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
        if max_fund_count is not None:
            q = q.where(Manager.current_fund_count <= max_fund_count)

        rows = self.db.execute(q).scalars().all()
        aggregates = self._load_aggregates([m.manager_id for m in rows])
        items = []
        for m in rows:
            dto = self._to_dto(m)
            dto.update(aggregates.get(m.manager_id, {}))
            items.append(dto)

        # 派生指标筛选（None 不命中，与 SQL 侧语义一致）
        if min_win_rate is not None:
            items = [it for it in items
                     if it["tenure_win_rate"] is not None and it["tenure_win_rate"] >= min_win_rate]
        if min_solo_ratio is not None:
            items = [it for it in items
                     if it["solo_ratio"] is not None and it["solo_ratio"] >= min_solo_ratio]

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
            "tenure_win_rate": lambda it: it["tenure_win_rate"],
            "current_weighted_annual": lambda it: it["current_weighted_annual"],
            "solo_ratio": lambda it: it["solo_ratio"],
            "name": lambda it: it["name"],
        }.get(sort, lambda it: it["weighted_annual"])

        valued = [it for it in items if getter(it) is not None]
        valued.sort(key=getter, reverse=descending)
        empty = [it for it in items if getter(it) is None]
        ordered = valued + empty

        total = len(items)
        offset = (page - 1) * limit
        return {"total": total, "items": ordered[offset:offset + limit]}

    def _load_aggregates(self, manager_ids: list[str]) -> dict[str, dict]:
        """批量算任期胜率 / 独管比例 / 代表作背离。

        任期胜率：有回报的任期里 return>0 的占比（`11-10` 口径：不设天数下限，
        与 weighted_annual 的 90 天地板是两回事——短段也是一段真实的业绩记录）。
        独管比例：is_current 任期中，该基金当前仅此一位经理的占比。
        """
        if not manager_ids:
            return {}

        # SQLAlchemy 把 sum(布尔) 的返回类型标成 Boolean（Python 侧只会拿到
        # True/False），必须用 case 显式转 0/1 整数再求和
        win_rows = self.db.execute(
            select(
                ManagerTenure.manager_id,
                func.count(ManagerTenure.id),
                func.sum(case((ManagerTenure.tenure_return > 0, 1), else_=0)),
            ).where(
                ManagerTenure.manager_id.in_(manager_ids),
                ManagerTenure.tenure_return.isnot(None),
            ).group_by(ManagerTenure.manager_id)
        ).all()
        win_rate: dict[str, Optional[float]] = {mid: None for mid in manager_ids}
        for mid, total, wins in win_rows:
            win_rate[mid] = round(wins * 100.0 / total, 1) if total else None

        # 当前在管：每只基金的经理人数（stock_active 经理范围内计数；
        # 共管判断只需要「是否 >1」，范围缩小不影响布尔结果）
        fund_mgr_rows = self.db.execute(
            select(ManagerTenure.fund_code, func.count(func.distinct(ManagerTenure.manager_id)))
            .join(Manager, Manager.manager_id == ManagerTenure.manager_id)
            .where(Manager.scope == "stock_active", ManagerTenure.is_current == True)  # noqa: E712
            .group_by(ManagerTenure.fund_code)
        ).all()
        fund_mgr_count = dict(fund_mgr_rows)

        cur_rows = self.db.execute(
            select(ManagerTenure.manager_id, ManagerTenure.fund_code)
            .where(ManagerTenure.manager_id.in_(manager_ids), ManagerTenure.is_current == True)  # noqa: E712
        ).all()
        cur_by_mgr: dict[str, list[str]] = defaultdict(list)
        for mid, code in cur_rows:
            cur_by_mgr[mid].append(code)

        solo_ratio: dict[str, Optional[float]] = {mid: None for mid in manager_ids}
        for mid, codes in cur_by_mgr.items():
            solo = sum(1 for c in codes if fund_mgr_count.get(c, 0) == 1)
            solo_ratio[mid] = round(solo * 100.0 / len(codes), 1)

        # 在管年化：is_current + 主动权益段的时长加权（口径同
        # manager_metrics.weighted_annual，只是范围收窄到在管段）。
        # 20k 行拉回 Python 判定 fund_type（排除规则是 Python 函数，SQL 化会丢精度）
        cur_annual_rows = self.db.execute(
            select(
                ManagerTenure.manager_id,
                ManagerTenure.fund_type,
                ManagerTenure.annual_return,
                ManagerTenure.tenure_days,
            ).where(
                ManagerTenure.manager_id.in_(manager_ids),
                ManagerTenure.is_current == True,  # noqa: E712
            )
        ).all()
        acc: dict[str, float] = defaultdict(float)
        days_sum: dict[str, float] = defaultdict(float)
        for mid, ftype, ann, days in cur_annual_rows:
            if not is_active_equity(ftype) or ann is None or not days or days <= 0:
                continue
            acc[mid] += ann * days
            days_sum[mid] += days
        current_annual: dict[str, Optional[float]] = {mid: None for mid in manager_ids}
        for mid in manager_ids:
            if days_sum[mid] > 0:
                current_annual[mid] = round(acc[mid] / days_sum[mid], 2)

        # 在管在榜数：在管基金 ∩ 夏普周观测（历史累计，上过任何一周即算）。
        # 观测表 distinct code 仅百余只，先取集合再内存交集，避免大 IN
        board_codes = set(self.db.execute(
            select(SharpeBoardObservation.code).distinct()
        ).scalars())
        board_on_current: dict[str, int] = {}
        for mid, codes in cur_by_mgr.items():
            board_on_current[mid] = sum(1 for c in codes if c in board_codes)

        return {
            mid: {
                "tenure_win_rate": win_rate[mid],
                "solo_ratio": solo_ratio[mid],
                "current_weighted_annual": current_annual[mid],
                "board_on_current": board_on_current.get(mid, 0),
                "current_fund_total": len(cur_by_mgr.get(mid, [])),
            }
            for mid in manager_ids
        }

    def get_detail(self, manager_id: str) -> dict | None:
        m = self.db.get(Manager, manager_id)
        if m is None:
            return None
        tenures = self.db.execute(
            select(ManagerTenure)
            .where(ManagerTenure.manager_id == manager_id)
            .order_by(ManagerTenure.tenure_days.desc())
        ).scalars().all()
        aggregates = self._load_aggregates([manager_id]).get(manager_id, {})
        affiliations = self._load_affiliations([t.fund_code for t in tenures])
        tenure_returns = self._load_tenure_returns([t.fund_code for t in tenures])
        return {
            **self._to_dto(m),
            **aggregates,
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
                    "affiliation": affiliations.get(t.fund_code),
                    **tenure_returns.get(t.fund_code, {}),
                }
                for t in tenures
            ],
        }

    def _load_tenure_returns(self, fund_codes: list[str]) -> dict[str, dict]:
        """任期基金的近 1 年 / 近 3 年 / 近 5 年收益 + 同类排名（与股票 tab 主表同口径）。

        数据源与股票 tab 一致，但顺序相反——这里以「基金自身口径」为准：
        - 收益：FundPerformance（雪球链路）优先，缺失回退 MarketFundRank（市场链路）
        - 排名：FundAchievementRank 的阶段业绩/近1年、近3年、近5年（同类分位）

        近 5 年只有 FundPerformance 一条链路：market_fund_rank 表没有 ret_5y 列
        （市场链路只到近3年/今年以来/成立以来），故无回退，缺失即为空。

        注意口径差异：任期内的「任职回报」按任职窗口算，而这里近 1/3/5 年是
        基金自身的时间窗口收益——两者对已离任的经理不必然一致
        （经理离任后基金可能换了人）。故命名用「近1年」而非「任职近1年」。
        """
        codes = [c for c in set(fund_codes) if c]
        if not codes:
            return {}

        # 收益：FundPerformance 优先，MarketFundRank 回退（仅近1年/近3年）
        ret_map: dict[str, tuple[float | None, float | None, float | None]] = {}
        perf_rows = self.db.execute(
            select(
                FundPerformance.code,
                FundPerformance.ret_1y,
                FundPerformance.ret_3y,
                FundPerformance.ret_5y,
            ).where(FundPerformance.code.in_(codes))
        ).all()
        for code, r1, r3, r5 in perf_rows:
            ret_map[code] = (r1, r3, r5)
        missing = [c for c in codes if c not in ret_map or ret_map[c] == (None, None, None)]
        if missing:
            rank_rows = self.db.execute(
                select(MarketFundRank.code, MarketFundRank.ret_1y, MarketFundRank.ret_3y)
                .where(MarketFundRank.code.in_(missing))
            ).all()
            for code, r1, r3 in rank_rows:
                prev = ret_map.get(code) or (None, None, None)
                ret_map[code] = (prev[0] if prev[0] is not None else r1,
                                 prev[1] if prev[1] is not None else r3,
                                 prev[2])

        # 同类排名：阶段业绩/近1年、近3年、近5年（与股票 tab RANK_PERIODS 同源）
        ach_rows = self.db.execute(
            select(
                FundAchievementRank.code,
                FundAchievementRank.period,
                FundAchievementRank.peer_rank,
            ).where(
                FundAchievementRank.code.in_(codes),
                FundAchievementRank.period_kind == "阶段业绩",
                FundAchievementRank.period.in_(("近1年", "近3年", "近5年")),
            )
        ).all()
        rank_map: dict[str, dict[str, dict | None]] = defaultdict(dict)
        for code, period, peer_rank in ach_rows:
            rank_map[code][period] = parse_peer_rank(peer_rank)

        out: dict[str, dict] = {}
        for code in codes:
            r1, r3, r5 = ret_map.get(code, (None, None, None))
            ranks = rank_map.get(code, {})
            out[code] = {
                "ret_1y": r1,
                "ret_3y": r3,
                "ret_5y": r5,
                "rank_1y": ranks.get("近1年"),
                "rank_3y": ranks.get("近3年"),
                "rank_5y": ranks.get("近5年"),
            }
        return out

    def _load_affiliations(self, fund_codes: list[str]) -> dict[str, dict | None]:
        """任期基金的跨 tab 归属（徽章数据，一次两条小查询）。

        - tab：老两 tab 按 yaml 名单成员（resolve universe），market 两 tab
          按 funds.market_type（债基·市场/股基·市场）。命中多个取优先级
          首个（老名单窄而精，优先于市场全量）。
        - board_weeks：该基金出现在夏普周观测的周数（历史累计）。
        - fund_name_market：funds 表的正式名称（tenures 的 name 是东财档案
          快照，可能过时）。
        """
        codes = [c for c in set(fund_codes) if c]
        if not codes:
            return {}

        # market 两 tab：funds.market_type（'bond'/'stock'，None=other）
        market_rows = self.db.execute(
            select(Fund.code, Fund.name, Fund.market_type).where(Fund.code.in_(codes))
        ).all()
        fund_info = {code: (name, mtype) for code, name, mtype in market_rows}

        # 老两 tab 名单：yaml 成员（缓存读文件，量小）
        bond_yaml = set(resolve_universe_codes("bond"))
        stock_yaml = set(resolve_universe_codes("stock"))

        # 在榜周数：code → count(weeks)
        board_rows = self.db.execute(
            select(SharpeBoardObservation.code, func.count(SharpeBoardObservation.id))
            .join(SharpeBoardWeek, SharpeBoardWeek.id == SharpeBoardObservation.week_id)
            .where(
                SharpeBoardObservation.code.in_(codes),
                SharpeBoardWeek.status == "complete",
            )
            .group_by(SharpeBoardObservation.code)
        ).all()
        board_weeks = dict(board_rows)

        out: dict[str, dict | None] = {}
        for code in codes:
            name, mtype = fund_info.get(code, (None, None))
            tab = None
            if code in bond_yaml:
                tab = "bond"
            elif code in stock_yaml:
                tab = "stock"
            elif mtype == "bond":
                tab = "discovery-bond"
            elif mtype == "stock":
                tab = "discovery-stock"
            weeks = board_weeks.get(code, 0)
            if tab is None and weeks == 0:
                out[code] = None
                continue
            out[code] = {
                "tab": tab,
                "board_weeks": weeks,
                "fund_name_market": name,
            }
        return out

    @staticmethod
    def _to_dto(m: Manager) -> dict:
        dto = {
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
        # 代表作背离（pp）：>15 说明业绩集中在单只代表作，展示层据此标记
        if dto["longest_tenure_annual"] is not None and dto["weighted_annual"] is not None:
            dto["rep_divergence"] = round(dto["longest_tenure_annual"] - dto["weighted_annual"], 1)
        else:
            dto["rep_divergence"] = None
        return dto

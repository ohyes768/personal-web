"""
夏普榜单本轮采集捕获（design：SharpeRunCapture）

只在两个股基周刷新链路中启用可选 capture 参数：
- stock 配置名单链路：src/scheduler/tasks.py refresh_stock_funds_sync
- 股基·市场链路：src/services/market_full_pipeline.py refresh_market_full_sync
  （经 market_risk_refresh.refresh 透传到 risk_service.refresh_fund_risks）

所有采集函数 capture=None（默认）时行为与返回值不变（旧路径零变更）。

关键语义（design「本轮采集与发布」）：
- capture 是纯内存快照：采集函数在本轮成功 commit 后把本轮写入的基础字段、
  universe 名单、风险值及实际样本尾日冻结进来；后续发布（步骤 3）只读
  capture，不重新读可能被普通刷新覆盖的最新共享行。
- 输入采集错误（网络失败、阶段失败）进 errors：本轮不得发布完整榜。
  risk_service._safe_fetch_nav 会吞异常返回空表，capture 路径单独保留
  失败证据，不能把网络失败当正常缺值。
- 数据有效但指标无定义（QDII 无基准、样本不足、回归退化）进 diagnostics：
  正常缺值，不入选但不算采集失败。
- base_rows 字段与 filter_service.entry_predicate 消费的属性对齐
  （age_years / size_yi / dd_3y 由发布侧经谓词评估；base_rows 冻结
  Fund 行字段，market_subtype 供 QDII 排除与市场子类成员判定）。
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from datetime import date, timedelta

from sqlalchemy import select

from src.db.models import Fund, FundAchievementRank, FundPerformance

# base_rows 冻结的 Fund 行字段（入选谓词评估所需 + 名称快照）。
# dd_3y 不在此列：它在 FundPerformance 行上，由 freeze_dd_rows 在本轮业绩
# commit 后就地合并进 base_rows（发布谓词的合并形态见发布侧文档）。
# mgr_experience_years_max（11-13-sharpe-board-v2-rules 修复）：entry_predicate
# 的 min_mgr_exp 优先读该列（共管取最长），缺了会静默回退到取最短而误杀
# 「老将+新人」组合——曾实测 0/97 的观测证据里带此字段。
BASE_ROW_FIELDS = (
    "name", "market_subtype", "age_years", "size_yi",
    "mgr_experience_years", "mgr_experience_years_max",
)

# v2 同类排名冻结口径（PRD R1 / design §2、§11）
PEER_PERIOD_KIND = "阶段业绩"
PEER_PERIOD = "近3年"
PEER_STALE_DAYS = 90          # as_of_date 距今超过 90 天视为无数据
_PEER_QUERY_CHUNK = 500       # SQLite 参数上限防御，批量 in_ 分块

# v3 年度同类排名口径（11-14-sharpe-board-v3-yearly-peer）
# 年度业绩排名是「某自然年的最终排名」，历史固定值 —— 与阶段业绩的滚动排名不同，
# 后者标题是「截至今天」、每次调用会变。实测：库内 as_of=2026-09-09 的 2023 年
# 排名与 2026-11-14 实时接口值逐字一致（3456/4165），故可安全用于历史回溯。
YEARLY_PERIOD_KIND = "年度业绩"
YEARLY_WINDOW = 3             # 取最近 3 个「已完成」自然年度
MIN_YEARLY_TOP_PCT = 25.0     # 单年分位 ≤25%（前 25%）算该年达标
MIN_YEARLY_YEARS = 2          # 3 年中至少 2 年达标

def yearly_window(ref_year: int | None = None, *, window: int = YEARLY_WINDOW) -> list[str]:
    """最近 window 个「已完成」自然年度（升序字符串）。

    今年未结束 → 从 ref_year-1 往前数。
      2026 → ["2023","2024","2025"]
      2027 → ["2024","2025","2026"]
    排除当年是刻意设计：当年只过了几个月，年度排名是「今年以来」的不完整
    排名，与完整年度不可比（用户明确要求「除开今年往前三年」）。
    """
    if ref_year is None:
        ref_year = date.today().year
    return [str(y) for y in range(ref_year - window, ref_year)]


@dataclass
class SharpeRunCapture:
    """一轮周刷新的本轮输入快照（步骤 3 发布时消费）。

    run_id：关联 RefreshRun.task_id（周榜行的 run_id 亦用它）。
    base_rows：code → Fund 行筛选字段快照（本轮 commit 后冻结）。
    risk_rows：code → 本轮风险值（含 returns_end_date），内存直存不回读 DB。
    errors：输入采集错误（网络失败 / 阶段失败 / 采集重试耗尽）。
      非空时本轮不得发布完整榜（记 failed，R6）。
    diagnostics：数据有效但指标无定义等非错误信息（如 metrics_undefined 列表）。
    universe_codes：本轮最终采集名单（市场链路为三段预筛后的 codes；
      雪球三分法为 yaml 名单）。按 code 去重由发布侧保证。
    filters / collection_prefilters：规则条件随 capture 保存的副本
      （filters 由创建方从 profile 填；collection_prefilters 由市场链路冻结）。
    peer_rows：code → 本轮近3年同类排名分位快照（v2 门槛证据；由
      freeze_peer_rows 批量冻结，发布只读冻结，不回读可能被 L5 覆盖的共享表）。
    """

    run_id: str
    base_rows: dict[str, dict] = field(default_factory=dict)
    risk_rows: dict[str, dict] = field(default_factory=dict)
    peer_rows: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)
    universe_codes: list[str] = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    collection_prefilters: dict = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        """记录一条输入采集错误（发布侧据 errors 非空判定本轮 failed）。"""
        self.errors.append(message)


def freeze_base_row(db: Session, code: str) -> dict | None:
    """本轮 commit 后读取该 code 的 Fund 行筛选字段快照。

    在采集函数 persist + commit 之后调用：读到的是本轮刚写入的值，
    后续普通刷新覆盖共享行不影响已冻结的 dict（纯拷贝）。
    Fund 行不存在（理论上不会：persist_snapshot 先写）返回 None。
    """
    fund = db.get(Fund, code)
    if fund is None:
        return None
    return {name: getattr(fund, name) for name in BASE_ROW_FIELDS}


def freeze_base_rows(db: Session, codes: list[str]) -> dict[str, dict]:
    """批量冻结（市场链路 L2 commit 后一次性冻结全部最终 codes）。"""
    out: dict[str, dict] = {}
    for code in codes:
        row = freeze_base_row(db, code)
        if row is not None:
            out[code] = row
    return out


def freeze_dd_rows(db: Session, base_rows: dict[str, dict]) -> None:
    """把 FundPerformance.dd_3y 补进已冻结的 base_rows（就地合并）。

    dd_3y 在 FundPerformance 行上（两条股基链路都写这张表：雪球三分法走
    persist_snapshot、市场链路走 L3 market_nav_refresh），freeze_base_row
    从 Fund 行冻结不到它。在本轮业绩 commit 后调用，读到的是本轮刚写入
    的值；发布只读 base_rows，不回读可能被普通刷新覆盖的共享行。
    base_rows 没有的 code（snapshot 失败，无本轮 Fund 行）跳过——这些
    code 本就不参评。
    """
    for code, row in base_rows.items():
        perf = db.get(FundPerformance, code)
        row["dd_3y"] = perf.dd_3y if perf is not None else None


def _parse_peer_percentile(raw: str | None) -> float | None:
    """'278/1951' → 14.25（rank/total*100）；格式异常 → None。

    独立于 filter_service._parse_peer_rank：本函数只要百分位数值，
    且不返回 dict，便于谓词直接比较（v2 max_peer_pct 门）。
    """
    if not raw or "/" not in raw:
        return None
    try:
        rank_s, total_s = raw.split("/", 1)
        rank = int(rank_s.strip())
        total = int(total_s.strip())
    except (ValueError, TypeError):
        return None
    if rank <= 0 or total <= 0 or rank > total:
        return None
    return round(rank / total * 100, 4)


def freeze_peer_rows(db: Session, codes: list[str], *, today: date | None = None) -> dict[str, dict]:
    """批量冻结近 3 年同类排名分位（v2 发布侧唯一 peer 数据来源）。

    为什么必须冻结：fund_achievement_rank 会被市场链路 L5 阶段
    delete+bulk insert 覆盖重写；发布时若回读该表，拿到的可能是下一轮数据。
    与 dd_3y 同一个「发布不回读共享行」契约（design §2、§11）。

    一次批量 in_ 查询（≤500 codes 分块），不做 per-code 查询。
    返回 {code: {"peer_pct": float, "peer_raw": str, "as_of": "YYYY-MM-DD"}}；
    以下情形不入字典（= 无数据 → 谓词 max_peer_pct 门不命中）：
      - 无记录 / peer_rank 为空或格式异常
      - as_of_date 距 today 超过 PEER_STALE_DAYS（90 天）
      - 陈旧判定用数据自带 as_of_date，不用写入时间（design §11 附带发现）

    today 可注入以便测试；默认 date.today()。
    """
    if today is None:
        today = date.today()
    stale_cutoff = today - timedelta(days=PEER_STALE_DAYS)

    out: dict[str, dict] = {}
    for start in range(0, len(codes), _PEER_QUERY_CHUNK):
        chunk = codes[start:start + _PEER_QUERY_CHUNK]
        if not chunk:
            continue
        rows = db.execute(
            select(
                FundAchievementRank.code,
                FundAchievementRank.peer_rank,
                FundAchievementRank.as_of_date,
            ).where(
                FundAchievementRank.code.in_(chunk),
                FundAchievementRank.period_kind == PEER_PERIOD_KIND,
                FundAchievementRank.period == PEER_PERIOD,
            )
        ).all()
        for code, raw, as_of in rows:
            if as_of is None or as_of < stale_cutoff:
                continue
            pct = _parse_peer_percentile(raw)
            if pct is None:
                continue
            out[code] = {
                "peer_pct": pct,
                "peer_raw": raw,
                "as_of": as_of.isoformat(),
            }
    return out


def freeze_yearly_peer_rows(
    db: Session,
    codes: list[str],
    *,
    ref_year: int | None = None,
    top_pct: float = MIN_YEARLY_TOP_PCT,
    min_years: int = MIN_YEARLY_YEARS,
) -> dict[str, dict]:
    """批量冻结「最近 N 个完整年度」的同类排名分位与达标情况（v3 唯一 peer 来源）。

    与 v2 的 freeze_peer_rows 的区别：
      - 用「年度业绩」而非「阶段业绩·近3年」（后者是滚动值，不可回溯）
      - **不做 as_of 陈旧判断**：年度排名是历史事实，不存在「过期」
      - 达标与否在冻结时算好（qualified/qualified_years），谓词只读布尔

    为什么达标要在冻结阶段算：谓词是纯函数、只做数值比较；阈值随 profile 版本
    可能变。把「当时用什么阈值、算出了什么」连同证据一起冻结，符合
    contracts §13「发布只读本轮冻结证据」的契约。

    一次批量 in_ 查询（500 codes 分块），禁止 per-code 查询。

    返回 {code: {
        "years": {"2023": 8.2, "2024": None, "2025": 12.5},  # 分位或 None
        "qualified_years": 2,       # 分位 ≤ top_pct 的年数
        "yearly_top_pct": 25.0,     # 本轮阈值快照
        "min_years": 2,             # 本轮达标年数门槛快照
        "qualified": True,          # qualified_years >= min_years
        "window": ["2023", "2024", "2025"],
    }}
    只有「至少一年有有效排名」的 code 才入字典；完全无数据的 code 不入
    （= 无证据 → 谓词不命中，并由发布侧计入 gate_missing 诊断）。
    """
    window = yearly_window(ref_year)
    out: dict[str, dict] = {}

    for start in range(0, len(codes), _PEER_QUERY_CHUNK):
        chunk = codes[start:start + _PEER_QUERY_CHUNK]
        if not chunk:
            continue
        rows = db.execute(
            select(
                FundAchievementRank.code,
                FundAchievementRank.period,
                FundAchievementRank.peer_rank,
            ).where(
                FundAchievementRank.code.in_(chunk),
                FundAchievementRank.period_kind == YEARLY_PERIOD_KIND,
                FundAchievementRank.period.in_(window),
            )
        ).all()

        # code → {year: pct or None}
        by_code: dict[str, dict[str, float | None]] = {}
        for code, period, raw in rows:
            if code not in by_code:
                by_code.setdefault(code, {})
            # 同一年可能有多行（不同 as_of 快照）：取第一个有效分位即可，
            # 年度排名本身是固定值，重复行是同值冗余。
            if by_code[code].get(period) is None:
                by_code[code][period] = _parse_peer_percentile(raw)

        for code, year_pcts in by_code.items():
            years = {y: year_pcts.get(y) for y in window}
            if all(v is None for v in years.values()):
                continue  # 窗口内全无有效数据 → 不入字典
            qualified_years = sum(
                1 for v in years.values() if v is not None and v <= top_pct
            )
            out[code] = {
                "years": years,
                "qualified_years": qualified_years,
                "yearly_top_pct": top_pct,
                "min_years": min_years,
                "qualified": qualified_years >= min_years,
                "window": list(window),
            }
    return out

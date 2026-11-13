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

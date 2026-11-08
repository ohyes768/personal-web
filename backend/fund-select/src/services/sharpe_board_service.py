"""
夏普榜单：规则 profile / canonical 副本 / 周键 / 周批次冻结语义 / 原子发布

规则语义（design / PRD）：
- 两套固定 profile：stock:v1（雪球三分法）、discovery-stock:v1（股基·市场），
  入选条件 = PRD 首版工程默认值（股基 tab 当前默认筛选）；市场来源另受
  现有采集预筛（三年收益 ≥20%、规模 ≥5 亿、经理 ≥5 年）约束。
- 规则变更必须换 version（v2…），不改旧周规则；每个周榜保存完整规则副本。
- 记录参数（filters 内 min_sharpe）与展示参数（min_latest_sharpe）分开；
  本模块只管记录规则。

发布编排（implement 步骤 3，design「本轮采集与发布」）：
- publish_week_board 只消费本轮 SharpeRunCapture 冻结数据，不回读可能被
  普通刷新覆盖的共享行；批次行 + 全部观测同一事务，中途失败整体 rollback。
- 判定顺序（R6）：同周已有 complete 冻结 → capture.errors 非空记 failed →
  冻结数据过入选谓词 → 有限 sharpe 才可写 → 相对上次发布样本尾日比对
  （全部无更新 skipped_no_new_data，个别无更新留空计诊断）→ complete。
"""
import copy
import hashlib
import json
import math
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.data.market_subtype_map import DISCOVERY_STOCK_SUBTYPES
from src.db.models import SharpeBoardObservation, SharpeBoardWeek
from src.services.filter_service import entry_predicate
from src.services.sharpe_capture import SharpeRunCapture

TIMEZONE = ZoneInfo("Asia/Shanghai")

# 周榜状态（design：complete|failed|skipped_no_new_data；running 复用 scheduler 内存态，不落表）
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"
STATUS_SKIPPED_NO_NEW_DATA = "skipped_no_new_data"
WEEK_STATUSES = {STATUS_COMPLETE, STATUS_FAILED, STATUS_SKIPPED_NO_NEW_DATA}

# 夏普算法口径（risk_service：近 3 年日频复权 vs TRI，√252 年化）；口径变更必须升版本
ALGORITHM_VERSION = "risk-3y-v1"

# 入选条件（PRD 首版工程默认值），参数名与 FilterService 对齐，供后续步骤共用谓词
_ENTRY_FILTERS = {
    "min_age": 3,         # 成立 ≥3 年
    "min_size_yi": 5,     # 规模 ≥5 亿
    "max_dd_3y": 30,      # 近三年回撤绝对值 ≤30%（库内负值按绝对值比较）
    "min_mgr_exp": 5,     # 经理从业 ≥5 年
    "min_sharpe": 0.8,    # 近三年夏普 ≥0.8（含等于）
    "exclude_qdii": False,
}

# 市场来源采集预筛（weekly_refresh 现值）
_MARKET_PREFILTERS = {"min_ret_3y": 20, "min_size_yi": 5, "min_mgr_exp": 5}


def _entry_filters() -> dict:
    return copy.deepcopy(_ENTRY_FILTERS)


# 两套固定 profile；键 (source, version)。market_subtypes 是市场来源的确定
# 副本（DISCOVERY_STOCK_SUBTYPES 快照），雪球三分法走 yaml 名单为 None。
SHARPE_BOARD_PROFILES: dict[tuple[str, str], dict] = {
    ("stock", "v1"): {
        "source": "stock",
        "version": "v1",
        "filters": _entry_filters(),
        "collection_prefilters": {},
        "market_subtypes": None,
        "algorithm_version": ALGORITHM_VERSION,
    },
    ("discovery-stock", "v1"): {
        "source": "discovery-stock",
        "version": "v1",
        "filters": _entry_filters(),
        "collection_prefilters": dict(_MARKET_PREFILTERS),
        "market_subtypes": list(DISCOVERY_STOCK_SUBTYPES),
        "algorithm_version": ALGORITHM_VERSION,
    },
}


def get_profile(source: str, version: str = "v1") -> dict:
    """规则 profile 深拷贝（调用方改动不污染常量）；未知组合 KeyError。"""
    return copy.deepcopy(SHARPE_BOARD_PROFILES[(source, version)])


def canonical_json(payload) -> str:
    """排序键 + 紧凑分隔符 + 中文不转义：同一规则任何构造顺序得到同一字节串。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(payload) -> str:
    """canonical JSON 的 sha256（十六进制），随榜保存用于检测规则漂移。"""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def recording_week(started_at: datetime) -> date:
    """任务开始时刻 → 北京时间所在 ISO 周的周一（跨周完成仍归开始周）。

    拒绝 naive datetime：不知道时区的执行时刻无法确定真实周（R7）。
    """
    if started_at.tzinfo is None:
        raise ValueError("started_at must be timezone-aware")
    local = started_at.astimezone(TIMEZONE).date()
    return local - timedelta(days=local.weekday())


def _to_utc_naive(dt: datetime) -> datetime:
    """aware datetime → UTC 挂钟 naive（SQLite DateTime 列约定存 UTC）。"""
    if dt.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return dt.astimezone(UTC).replace(tzinfo=None)


def get_board_week(
    db: Session, source: str, profile_version: str, week_start: date,
) -> SharpeBoardWeek | None:
    """按 (source, version, week) 取周批次行。"""
    stmt = select(SharpeBoardWeek).where(
        SharpeBoardWeek.source == source,
        SharpeBoardWeek.profile_version == profile_version,
        SharpeBoardWeek.week_start == week_start,
    )
    return db.execute(stmt).scalars().first()


def _write_week_attempt(
    db: Session,
    *,
    source: str,
    profile_version: str,
    week_start: date,
    status: str,
    started_at: datetime,
    finished_at: datetime | None = None,
    run_id: str | None = None,
    trigger: str | None = None,
    selected_count: int = 0,
    errors: list[str] | None = None,
    diagnostics: dict | None = None,
) -> tuple[SharpeBoardWeek, bool]:
    """写入/更新一次周榜尝试（冻结语义），不 commit；返回 (周行, 是否写入)。

    - 同 (source, version, week) 已有 complete 行 → 不动已有数据，返回 (已有行, False)
      （complete 后不可重写；每次尝试仍留现有 JSONL 审计）
    - 无行或已有 failed/skipped 行 → 覆盖为本次尝试（同周重试），成功后旧错误清空
    - started_at/finished_at 要求 timezone-aware（UTC 保存）；published_at 仅 complete 写入
    - flush 取主键但不 commit：发布侧在同一事务内追加全部观测后统一提交
    """
    if status not in WEEK_STATUSES:
        raise ValueError(f"unknown week status: {status}")
    profile = get_profile(source, profile_version)

    existing = get_board_week(db, source, profile_version, week_start)
    if existing is not None and existing.status == STATUS_COMPLETE:
        return existing, False

    row = existing if existing is not None else SharpeBoardWeek(
        source=source, profile_version=profile_version, week_start=week_start,
    )
    row.profile_json = canonical_json(profile)
    row.profile_hash = canonical_hash(profile)
    row.algorithm_version = profile["algorithm_version"]
    row.status = status
    row.run_id = run_id
    row.trigger = trigger
    row.started_at = _to_utc_naive(started_at)
    row.finished_at = _to_utc_naive(finished_at) if finished_at is not None else None
    row.published_at = datetime.now(UTC).replace(tzinfo=None) if status == STATUS_COMPLETE else None
    row.selected_count = selected_count
    row.errors_json = json.dumps(errors, ensure_ascii=False) if errors is not None else None
    row.diagnostics_json = (
        json.dumps(diagnostics, ensure_ascii=False) if diagnostics is not None else None
    )
    db.add(row)
    db.flush()
    return row, True


def record_week_attempt(
    db: Session,
    **kwargs,
) -> tuple[SharpeBoardWeek, bool]:
    """_write_week_attempt + 立即 commit（单次尝试写入即落库）。

    发布路径（publish_week_board）不用本函数：批次行 + 观测必须同一事务。
    """
    row, written = _write_week_attempt(db, **kwargs)
    db.commit()
    return row, written


def _finite(value) -> bool:
    """只接受有限数（NULL/NaN/Infinity 一律不写观测，bool 不是数值）。"""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _make_observation(
    week_id: int, code: str, base: dict, risk: dict, run_id: str,
) -> SharpeBoardObservation:
    """由本轮冻结数据构造观测行（调用方先经 _finite 校验 sharpe）。

    name 是入选时名称快照；evidence 保存本轮筛选字段值 + 来源刷新 ID。
    metric_calculated_at/returns_end_date 本轮未知时留空（R7 不伪造日期）。
    """
    calculated_at = risk.get("calculated_at")
    return SharpeBoardObservation(
        week_id=week_id,
        code=code,
        name=base.get("name") or "",
        sharpe=float(risk["sharpe"]),
        metric_calculated_at=(
            _to_utc_naive(calculated_at) if calculated_at is not None else None
        ),
        returns_end_date=risk.get("returns_end_date"),
        sample_days=risk.get("sample_days"),
        evidence_json=canonical_json({
            "risk_run_id": run_id,
            "base": base,
            "benchmark_source": risk.get("benchmark_source"),
        }),
    )


def _previous_returns_end_dates(
    db: Session, source: str, profile_version: str, week_start: date,
) -> dict[str, date]:
    """上次发布（最新 complete 周且早于本周）各基金的样本尾日；首次发布为空。"""
    prev_week = db.execute(
        select(SharpeBoardWeek).where(
            SharpeBoardWeek.source == source,
            SharpeBoardWeek.profile_version == profile_version,
            SharpeBoardWeek.status == STATUS_COMPLETE,
            SharpeBoardWeek.week_start < week_start,
        ).order_by(SharpeBoardWeek.week_start.desc()).limit(1)
    ).scalars().first()
    if prev_week is None:
        return {}
    rows = db.execute(
        select(SharpeBoardObservation).where(
            SharpeBoardObservation.week_id == prev_week.id,
        )
    ).scalars().all()
    return {r.code: r.returns_end_date for r in rows if r.returns_end_date is not None}


def publish_week_board(
    db: Session,
    *,
    source: str,
    profile_version: str,
    capture: SharpeRunCapture,
    trigger: str | None = None,
    started_at: datetime,
    finished_at: datetime | None = None,
) -> tuple[SharpeBoardWeek, bool]:
    """把一轮采集 capture 原子发布为当前周榜；返回 (周行, 是否新写入)。

    周键取任务 started_at（北京时间所在 ISO 周周一），不用 finished_at
    （跨周完成仍归开始周）。判定顺序（R6/R8）：

    1. 同周已有 complete → 冻结不覆盖、不重复计次，返回 (已有行, False)
    2. capture.errors 非空（nav 网络失败 / 阶段失败 / 基准风险错误）→
       记 failed、不写观测（returned failed 会漏报，capture 是唯一证据渠道）
    3. 采集范围为空（universe 无 codes：名单没抓到 / 预筛无命中）→ failed，
       不发空榜冒充零入选
    4. 冻结数据过入选谓词（与实时筛选同一份 entry_predicate；universe 按
       code 去重；市场来源再按规则副本 subtype 做成员防御过滤）；无本轮
       证据（base/risk 缺失）不参评，计 diagnostics
    5. sharpe 非有限数（NaN/Infinity/None）不写观测，计 diagnostics
    6. 样本尾日相对上次发布无更新的基金不写新点：全部无更新 →
       skipped_no_new_data；个别无更新 → 留空计 diagnostics（首次发布没有
       「上次」，直接正常发布）；有效全量输入零入选 → complete 空榜
    7. complete：批次行 + 全部观测同一事务提交，中途失败整体 rollback；
       并发唯一冲突时返回已有 complete（保留首个）
    """
    if started_at.tzinfo is None:
        raise ValueError("started_at must be timezone-aware")
    profile = get_profile(source, profile_version)
    week_start = recording_week(started_at)

    existing = get_board_week(db, source, profile_version, week_start)
    if existing is not None and existing.status == STATUS_COMPLETE:
        return existing, False

    if capture.errors:
        row, _ = _write_week_attempt(
            db, source=source, profile_version=profile_version, week_start=week_start,
            status=STATUS_FAILED, started_at=started_at, finished_at=finished_at,
            run_id=capture.run_id, trigger=trigger, selected_count=0,
            errors=list(capture.errors),
            diagnostics=dict(capture.diagnostics) or None,
        )
        db.commit()
        return row, True

    if not capture.universe_codes:
        # 本轮采集范围为空（名单没抓到 / 预筛无命中）：无效输入，不发空榜
        # 冒充「成功零入选」（R6；空名单失败与 contracts 分类语义一致）
        row, _ = _write_week_attempt(
            db, source=source, profile_version=profile_version, week_start=week_start,
            status=STATUS_FAILED, started_at=started_at, finished_at=finished_at,
            run_id=capture.run_id, trigger=trigger, selected_count=0,
            errors=["universe empty: no codes collected this run"],
        )
        db.commit()
        return row, True

    diagnostics: dict = dict(capture.diagnostics)
    predicate = entry_predicate(**profile["filters"])
    subtypes = profile.get("market_subtypes")
    subtype_set = set(subtypes) if subtypes is not None else None

    selected: list[dict] = []
    missing: list[str] = []
    for code in dict.fromkeys(capture.universe_codes):  # 按 code 去重，不受页长限制
        base = capture.base_rows.get(code)
        risk = capture.risk_rows.get(code)
        if base is None or risk is None:
            # 无本轮证据（snapshot 失败 / nav 失败）不参评不写观测；
            # 正常已在 capture.errors，这里防御计诊断
            missing.append(code)
            continue
        if subtype_set is not None and base.get("market_subtype") not in subtype_set:
            continue
        if predicate({**base, "sharpe": risk.get("sharpe")}):
            selected.append({"code": code, "base": base, "risk": risk})
    if missing:
        diagnostics["missing_evidence"] = missing

    writable = [s for s in selected if _finite(s["risk"].get("sharpe"))]
    invalid = [s["code"] for s in selected if not _finite(s["risk"].get("sharpe"))]
    if invalid:
        diagnostics["invalid_sharpe"] = invalid

    prev_map = _previous_returns_end_dates(db, source, profile_version, week_start)
    fresh: list[dict] = []
    stale_codes: list[str] = []
    for s in writable:
        end = s["risk"].get("returns_end_date")
        prev = prev_map.get(s["code"])
        if end is not None and prev is not None and end <= prev:
            stale_codes.append(s["code"])  # 样本无更新：不写新点，留空断线
        else:
            fresh.append(s)
    if stale_codes:
        diagnostics["stale_codes"] = stale_codes

    if prev_map and writable and not fresh:
        # 全部入选者样本尾日相对上次发布无更新 → 本周无新信息，
        # 不冒充榜、不重复抄旧值（design「本轮采集与发布」第 5 条）
        row, _ = _write_week_attempt(
            db, source=source, profile_version=profile_version, week_start=week_start,
            status=STATUS_SKIPPED_NO_NEW_DATA, started_at=started_at,
            finished_at=finished_at, run_id=capture.run_id, trigger=trigger,
            selected_count=0, diagnostics=diagnostics or None,
        )
        db.commit()
        return row, True

    # 原子发布：批次行 + 全部观测同一事务，观测构造/提交任一环失败整体
    # rollback（库里无半个榜）
    row, written = _write_week_attempt(
        db, source=source, profile_version=profile_version, week_start=week_start,
        status=STATUS_COMPLETE, started_at=started_at, finished_at=finished_at,
        run_id=capture.run_id, trigger=trigger, selected_count=len(fresh),
        diagnostics=diagnostics or None,
    )
    try:
        if written:
            for s in fresh:
                db.add(_make_observation(row.id, s["code"], s["base"], s["risk"], capture.run_id))
        db.commit()
    except IntegrityError:
        db.rollback()
        # 并发同周发布冲突：保留首个 complete，不重复计次
        existing = get_board_week(db, source, profile_version, week_start)
        if existing is not None and existing.status == STATUS_COMPLETE:
            return existing, False
        raise
    except Exception:
        db.rollback()
        raise
    return row, written


# ─────────────────────────────────────────────────────────────
# 只读聚合（implement 步骤 4：design「API 与统计合同」）
# ─────────────────────────────────────────────────────────────

# range → 周历起点向前裁剪的自然日数（all 不裁）。只裁图，不改任何统计。
_RANGE_DAYS: dict[str, int | None] = {"all": None, "3m": 91, "6m": 182, "1y": 365}


def _current_week() -> date:
    """当前北京时间自然周的周一（周历终点；测试 patch 此函数固定当前周）。"""
    local = datetime.now(TIMEZONE).date()
    return local - timedelta(days=local.weekday())


def _to_shanghai(dt: datetime) -> datetime:
    """UTC 挂钟 naive → 北京时间 aware（存储契约：存 UTC，展示北京时间）。"""
    return dt.replace(tzinfo=UTC).astimezone(TIMEZONE)


def _attempt_payload(row: SharpeBoardWeek) -> dict:
    """周批次尝试行 → latest_attempt DTO 载荷（错误原文透出，R6/R7）。"""
    return {
        "week_start": row.week_start,
        "status": row.status,
        "trigger": row.trigger,
        "started_at": _to_shanghai(row.started_at),
        "finished_at": _to_shanghai(row.finished_at) if row.finished_at else None,
        "selected_count": row.selected_count,
        "errors": json.loads(row.errors_json) if row.errors_json else [],
    }


def aggregate_board(
    db: Session,
    *,
    source: str,
    profile_version: str = "v1",
    min_latest_sharpe: float | None = None,
    min_weeks: int = 1,
    latest_only: bool = False,
    range_key: str = "all",
    page: int = 1,
    limit: int = 50,
) -> dict:
    """夏普榜单聚合：全历史聚合 → 展示筛选 → 排序 → total → 周历/series → 分页切片。

    - 统计（listed_weeks/latest_sharpe/last_listed_week/consecutive_weeks）只按
      当前 source/version 的 complete 周全历史计算；range 只裁周历（图），
      不改累计周数、最近上榜值和命中集合（下限判断用全历史最新记录）。
    - latest_only 用当前来源最新 complete 周榜（不是各基金最后一次记录周）；
      最新 complete 空榜 → 命中零只。
    - series 为全部命中基金，不随 items 分页；范围内无点保留 null 不造点。
    - 不 JOIN 实时 Fund 表（失活/清盘基金历史仍在）；300 只×104 周预算内
      Python 内存聚合，不截断。
    """
    if range_key not in _RANGE_DAYS:
        raise ValueError(f"unknown range: {range_key}")
    profile = get_profile(source, profile_version)

    week_rows = db.execute(
        select(SharpeBoardWeek).where(
            SharpeBoardWeek.source == source,
            SharpeBoardWeek.profile_version == profile_version,
        ).order_by(SharpeBoardWeek.week_start.asc())
    ).scalars().all()
    complete_weeks = [w for w in week_rows if w.status == STATUS_COMPLETE]
    complete_by_week = {w.week_start: w for w in complete_weeks}
    latest_complete = complete_weeks[-1] if complete_weeks else None

    # 全历史观测（观测只在发布 complete 时写入，天然无 failed/skipped 值）
    entries: dict[str, list[tuple[date, SharpeBoardObservation]]] = {}
    if complete_weeks:
        rows = db.execute(
            select(SharpeBoardWeek.week_start, SharpeBoardObservation)
            .join(SharpeBoardObservation, SharpeBoardObservation.week_id == SharpeBoardWeek.id)
            .where(
                SharpeBoardWeek.source == source,
                SharpeBoardWeek.profile_version == profile_version,
                SharpeBoardWeek.status == STATUS_COMPLETE,
            )
            .order_by(SharpeBoardWeek.week_start.asc(), SharpeBoardObservation.code.asc())
        ).all()
        for week_start, obs in rows:
            entries.setdefault(obs.code, []).append((week_start, obs))

    # 最新 complete 周榜成员（latest_only / on_latest_board 共用）
    latest_codes: set[str] = set()
    if latest_complete is not None:
        latest_codes = set(db.execute(
            select(SharpeBoardObservation.code).where(
                SharpeBoardObservation.week_id == latest_complete.id,
            )
        ).scalars().all())

    # 1) 全历史聚合 per code（name 用最近上榜观测的名称快照）
    stats: dict[str, dict] = {}
    for code, eps in entries.items():
        eps.sort(key=lambda e: e[0])
        last_week, last_obs = eps[-1]
        week_set = {w for w, _ in eps}
        consecutive = 0
        w = last_week
        while w in week_set:  # 缺席/未知周中断（design：最近一段连续在榜周数）
            consecutive += 1
            w -= timedelta(days=7)
        stats[code] = {
            "code": code,
            "name": last_obs.name,
            "listed_weeks": len(eps),
            "consecutive_weeks": consecutive,
            "latest_sharpe": last_obs.sharpe,
            "last_listed_week": last_week,
            "on_latest_board": code in latest_codes,
            "week_sharpe": dict(eps),
        }

    # 2) 展示筛选（全历史；下限含等于，R5）
    matched = [
        s for s in stats.values()
        if s["listed_weeks"] >= min_weeks
        and (min_latest_sharpe is None or s["latest_sharpe"] >= min_latest_sharpe)
        and (not latest_only or s["code"] in latest_codes)
    ]

    # 3) 排序：在榜周数降序 → 最近上榜夏普降序 → 代码升序（R3）
    matched.sort(key=lambda s: (-s["listed_weeks"], -s["latest_sharpe"], s["code"]))

    # 4) total 在切片前算；items 切片在排序后（contracts 分页不变量）
    total = len(matched)
    offset = (page - 1) * limit
    item_keys = ("code", "name", "listed_weeks", "consecutive_weeks",
                 "latest_sharpe", "last_listed_week", "on_latest_board")
    items_page = [{k: s[k] for k in item_keys} for s in matched[offset:offset + limit]]

    # 4b) 展示补充：近 1 年/近 3 年收益（仅展示，不参与统计/排序/命中集合）。
    #     FundPerformance（雪球链路）优先，缺失回退 MarketFundRank（市场链路）；
    #     只查当前页 codes，失活基金无行则留 null 不造数。
    page_codes = [it["code"] for it in items_page]
    ret_map: dict[str, tuple[float | None, float | None]] = {}
    if page_codes:
        from src.db.models import FundPerformance, MarketFundRank
        perf_rows = db.execute(
            select(FundPerformance.code, FundPerformance.ret_1y, FundPerformance.ret_3y)
            .where(FundPerformance.code.in_(page_codes))
        ).all()
        for code, r1, r3 in perf_rows:
            ret_map[code] = (r1, r3)
        missing = [c for c in page_codes if c not in ret_map or ret_map[c] == (None, None)]
        if missing:
            rank_rows = db.execute(
                select(MarketFundRank.code, MarketFundRank.ret_1y, MarketFundRank.ret_3y)
                .where(MarketFundRank.code.in_(missing))
            ).all()
            for code, r1, r3 in rank_rows:
                prev = ret_map.get(code) or (None, None)
                ret_map[code] = (prev[0] if prev[0] is not None else r1,
                                 prev[1] if prev[1] is not None else r3)
    for it in items_page:
        r1, r3 = ret_map.get(it["code"], (None, None))
        it["ret_1y"] = r1
        it["ret_3y"] = r3

    # 5) 周历：首次观测周 → 当前自然周；range 只裁起点，缺席/失败/停机留位
    current = _current_week()
    first_obs_week = min((eps[0][0] for eps in entries.values()), default=None)
    weeks: list[date] = []
    if first_obs_week is not None and first_obs_week <= current:
        cutoff_days = _RANGE_DAYS[range_key]
        if cutoff_days:
            start = current - timedelta(days=cutoff_days)
            # 裁剪起点对齐回周一网格：365=52周+1 天会使起点落到周日，
            # 周历整体脱离周一键后观测值对位全部落空（range 只裁起点，终点仍为当前周）
            start -= timedelta(days=start.weekday())
        else:
            start = first_obs_week
        start = max(first_obs_week, start)
        w = start
        while w <= current:
            weeks.append(w)
            w += timedelta(days=7)

    # 6) series：全部命中基金（不随分页），values 与裁剪后周历对齐；无点不造点
    series = [
        {
            "code": s["code"],
            "name": s["name"],
            "values": [
                s["week_sharpe"][w].sharpe if w in s["week_sharpe"] else None
                for w in weeks
            ],
        }
        for s in matched
    ]

    # 7) 状态与诊断：latest_attempt 是最新尝试行（任意状态）；当前周无 complete
    #    榜即 stale（失败/停机/未跑，不冒充本周，R6/R7）
    latest_attempt = week_rows[-1] if week_rows else None
    diagnostics = {
        "no_board_weeks": [w for w in weeks if w not in complete_by_week],
        "latest_diagnostics": (
            json.loads(latest_attempt.diagnostics_json)
            if latest_attempt is not None and latest_attempt.diagnostics_json else {}
        ),
    }

    return {
        "profile": profile,
        "latest_published_week": latest_complete.week_start if latest_complete else None,
        "latest_attempt": _attempt_payload(latest_attempt) if latest_attempt else None,
        "stale": current not in complete_by_week,
        "total": total,
        "items": items_page,
        "weeks": weeks,
        "series": series,
        "diagnostics": diagnostics,
    }

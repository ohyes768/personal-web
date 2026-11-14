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
# v2：入选门槛加 IR / 样本天数 / 同类分位三道门（11-13-sharpe-board-v2-rules）
ALGORITHM_VERSION_V2 = "risk-3y-v2"
# v3：同类分位改用年度口径（11-14-sharpe-board-v3-yearly-peer）
ALGORITHM_VERSION_V3 = "risk-3y-v3"

# 入选条件（PRD 首版工程默认值），参数名与 FilterService 对齐，供后续步骤共用谓词
_ENTRY_FILTERS = {
    "min_age": 3,         # 成立 ≥3 年
    "min_size_yi": 5,     # 规模 ≥5 亿
    "max_dd_3y": 30,      # 近三年回撤绝对值 ≤30%（库内负值按绝对值比较）
    "min_mgr_exp": 5,     # 经理从业 ≥5 年
    "min_sharpe": 0.8,    # 近三年夏普 ≥0.8（含等于）
    "exclude_qdii": False,
}

# v2 新增三道门（PRD R1）。参数改值 = 改版本，历史 v1 周行不受影响。
_V2_EXTRA_FILTERS = {
    "min_ir": 0.5,          # 信息比率 ≥0.5（跑赢基准效率）
    "min_sample_days": 700, # 样本交易日 ≥700（3 年约 750，留缺口余量）
    "max_peer_pct": 20.0,   # 近 3 年同类排名前 20%（分位 ≤20%）
}

# v3：把 v2 的滚动同类分位（max_peer_pct）换成年度口径。
# 年度排名是历史固定值，故周榜历史可回溯（v2 的滚动排名不行）。
# 实测（2026-11-14，当前 36 只 v2 成员）：前25%至少2年 → 保留 29 只（81%）。
_V3_EXTRA_FILTERS = {
    "min_ir": 0.5,             # 沿用 v2：信息比率 ≥0.5
    "min_sample_days": 700,    # 沿用 v2：样本交易日 ≥700
    "min_yearly_top_pct": 25.0,  # 单年同类分位 ≤25% 算该年达标
    "min_yearly_years": 2,     # 最近 3 个完整年度中至少 2 年达标
}

# 市场来源采集预筛（weekly_refresh 现值）
_MARKET_PREFILTERS = {"min_ret_3y": 20, "min_size_yi": 5, "min_mgr_exp": 5}


def _entry_filters() -> dict:
    """v1 五条件深拷贝（v1 profile 与 v2 的基底都用这一份，勿单改）。"""
    return copy.deepcopy(_ENTRY_FILTERS)


def _v3_filters() -> dict:
    """v1 五条件 + v3 四道门（IR/样本天数/年度分位阈值/年度达标年数）。

    注意：v3 **不含** max_peer_pct（滚动口径），改用 min_yearly_* 两个参数。
    两者不可混用，语义不同（单分位 ≤X vs N年中M年达标）。
    """
    filters = _entry_filters()
    filters.update(copy.deepcopy(_V3_EXTRA_FILTERS))
    return filters


def _v2_filters() -> dict:
    """v1 五条件 + 三道新门（v2 是 v1 的超集，不是另起一套）。"""
    filters = _entry_filters()
    filters.update(copy.deepcopy(_V2_EXTRA_FILTERS))
    return filters


# 固定 profile；键 (source, version)。market_subtypes 是市场来源的确定
# 副本（DISCOVERY_STOCK_SUBTYPES 快照），雪球三分法走 yaml 名单为 None。
# ⚠ v1 两条必须保持一字不改：v1 历史周行的 profile_json 按当时规则冻结，
#   改这里会让新读到的 v1 profile 与已落库快照不一致（契约 §13）。
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
    ("stock", "v2"): {
        "source": "stock",
        "version": "v2",
        "filters": _v2_filters(),
        "collection_prefilters": {},
        "market_subtypes": None,
        "algorithm_version": ALGORITHM_VERSION_V2,
    },
    ("discovery-stock", "v2"): {
        "source": "discovery-stock",
        "version": "v2",
        "filters": _v2_filters(),
        "collection_prefilters": dict(_MARKET_PREFILTERS),
        "market_subtypes": list(DISCOVERY_STOCK_SUBTYPES),
        "algorithm_version": ALGORITHM_VERSION_V2,
    },
    ("stock", "v3"): {
        "source": "stock",
        "version": "v3",
        "filters": _v3_filters(),
        "collection_prefilters": {},
        "market_subtypes": None,
        "algorithm_version": ALGORITHM_VERSION_V3,
    },
    ("discovery-stock", "v3"): {
        "source": "discovery-stock",
        "version": "v3",
        "filters": _v3_filters(),
        "collection_prefilters": dict(_MARKET_PREFILTERS),
        "market_subtypes": list(DISCOVERY_STOCK_SUBTYPES),
        "algorithm_version": ALGORITHM_VERSION_V3,
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
    peer: dict | None = None,
) -> SharpeBoardObservation:
    """由本轮冻结数据构造观测行（调用方先经 _finite 校验 sharpe）。

    name 是入选时名称快照；evidence 保存本轮筛选字段值 + 来源刷新 ID。
    peer（v2）：本轮冻结的同类排名分位快照，写进 evidence 供聚合展示，
    v1 无此数据传 None 保持旧 evidence 结构。
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
            "risk": {
                "ir": risk.get("ir"),
                "sample_days": risk.get("sample_days"),
            },
            "peer": peer,
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
    prof_filters = profile["filters"]
    # min_yearly_top_pct 不是谓词参数：它是冻结阶段算 qualified_years 用的阈值
    # （已随 peer_rows 冻结），谓词只需读算好的 qualified_years。
    predicate_kwargs = {
        k: v for k, v in prof_filters.items() if k != "min_yearly_top_pct"
    }
    predicate = entry_predicate(**predicate_kwargs)
    subtypes = profile.get("market_subtypes")
    subtype_set = set(subtypes) if subtypes is not None else None
    # 三道门前置值（v1 profile 不含这些参数 → 谓词整段跳过，行为不变）
    gates = {
        "ir": prof_filters.get("min_ir"),
        "sample_days": prof_filters.get("min_sample_days"),
        "peer": prof_filters.get("max_peer_pct"),          # v2 滚动口径
        "yearly": prof_filters.get("min_yearly_years"),    # v3 年度口径
    }

    selected: list[dict] = []
    missing: list[str] = []
    gate_missing: dict[str, list[str]] = {}
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
        peer = capture.peer_rows.get(code)
        # 诊断：区分「数据缺失」与「不达标」。缺失单独记，不达标不记
        # （不达标是正常筛选结果，进诊断会淹没真正的采集问题）。
        for gate_name, threshold in gates.items():
            if threshold is None:
                continue
            if gate_name == "peer":
                value = (peer or {}).get("peer_pct")
            elif gate_name == "yearly":
                # 年度口径：qualified_years 缺失才算「无证据」
                value = (peer or {}).get("qualified_years")
            else:
                value = risk.get(gate_name)
            if value is None:
                gate_missing.setdefault(gate_name, []).append(code)
        pred_input = {
            **base,
            "sharpe": risk.get("sharpe"),
            "ir": risk.get("ir"),
            "sample_days": risk.get("sample_days"),
            "peer_pct": (peer or {}).get("peer_pct"),            # v2
            "qualified_years": (peer or {}).get("qualified_years"),  # v3
        }
        if predicate(pred_input):
            selected.append({"code": code, "base": base, "risk": risk, "peer": peer})
    if missing:
        diagnostics["missing_evidence"] = missing
    if gate_missing:
        diagnostics["gate_missing"] = gate_missing

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
                db.add(_make_observation(
                    row.id, s["code"], s["base"], s["risk"], capture.run_id,
                    peer=s.get("peer"),
                ))
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

# 52 周窗口（11-13-sharpe-board-v2-rules）：榜单统计与图表统一卡在最近一年。
# 364 = 52×7 恰为 7 的倍数，起点天然落在周一网格上；旧 range=1y 用 365 天
# （52 周+1 天）会让起点落周日、series 全 null（契约 §13 记录过该回归）。
WINDOW_WEEKS = 52
QUALIFIED_SHARPE = 0.8          # 近12周「达标」的绝对参考线（与入选规则解耦）
NEAR_WEEKS = 12                 # 近12周达标统计窗口

# range → 窗口内缩放的周数（含当前周）。all/1y 等价 = 完整 52 周窗口。
# 相对旧的 _RANGE_DAYS（自然日）：1y 从 365 天改为整 52 周，顺手治好对齐缺陷。
_RANGE_WEEKS: dict[str, int] = {"all": 52, "1y": 52, "6m": 26, "3m": 13}


def _window_start(current: date) -> date:
    """当前周周一往前数 51 个周一（含当前周共 52 个周一）。"""
    return current - timedelta(weeks=WINDOW_WEEKS - 1)


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
    profile_version: str = "v3",
    min_latest_sharpe: float | None = None,
    min_weeks: int = 1,
    latest_only: bool = False,
    range_key: str = "all",
    page: int = 1,
    limit: int = 50,
) -> dict:
    """夏普榜单聚合：52 周窗口内聚合 → 展示筛选 → 排序 → total → 周历/series → 分页。

    v2（11-13-sharpe-board-v2-rules）口径变更：
    - 统计（listed_weeks / consecutive_weeks / latest_sharpe / near_12w）只按
      **最近 52 周**的 complete 周计算，窗口外数据不参与（但不删除观测行）。
      窗口起点 = 当前周 - 51 周，恰为周一网格（364 天 = 52×7）。
    - range 语义收窄为窗口内缩放：all/1y=52 周、6m=26 周、3m=13 周，
      起点取 max(window_start, range_start)，绝不让用户看到超出 52 周的数据。
    - latest_only 用当前来源最新 complete 周榜；最新空榜 → 命中零只。
    - series 为全部命中基金，不随分页；范围内无点保留 null 不造点。
    - 窗口截断后一年没上榜的基金 listed_weeks=0 → 被 min_weeks=1 默认筛掉
      （PRD R5 已声明为预期的连带后果）。
    - 不 JOIN 实时 Fund 表（失活/清盘基金历史仍在）。
    """
    if range_key not in _RANGE_WEEKS:
        raise ValueError(f"unknown range: {range_key}")
    profile = get_profile(source, profile_version)
    current = _current_week()
    window_start = _window_start(current)

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

    # 1) 52 周窗口内聚合 per code（name 用窗口内最近上榜观测的名称快照）
    stats: dict[str, dict] = {}
    for code, eps in entries.items():
        eps.sort(key=lambda e: e[0])
        # 窗口截断：只保留最近 52 周的观测，历史行仍在库里但不参与统计
        eps_in = [(w, o) for w, o in eps if w >= window_start]
        if not eps_in:
            # 只在窗口外上榜过 → listed_weeks=0，由 min_weeks 默认筛掉
            stats[code] = {
                "code": code, "name": eps[0][1].name,
                "listed_weeks": 0, "consecutive_weeks": 0,
                "latest_sharpe": None, "last_listed_week": None,
                "on_latest_board": code in latest_codes,
                "week_sharpe": {},
                "near_12w_qualified": None, "near_12w_total": None,
                "peer_pct": None, "peer_as_of": None,
                "peer_years": None, "peer_qualified_years": None,
                "peer_window": None,
            }
            continue
        last_week, last_obs = eps_in[-1]
        week_set = {w for w, _ in eps_in}
        consecutive = 0
        w = last_week
        while w in week_set and w >= window_start:
            # 连续段跨窗口边界时截断（design §5.0）
            consecutive += 1
            w -= timedelta(days=7)
        recent = eps_in[-NEAR_WEEKS:]
        # 同类排名证据：取窗口内最新一条带 peer 数据的观测。
        # v2 冻结的是 {peer_pct, as_of}（滚动口径）；v3 是
        # {years, qualified_years, window}（年度口径）。两者字段不同，
        # 分别读取以同时支持两个版本的展示。
        peer_pct = None
        peer_as_of = None
        peer_years = None
        peer_qualified_years = None
        peer_window = None
        for _, o in reversed(eps_in):
            if not o.evidence_json:
                continue
            try:
                ev = json.loads(o.evidence_json)
            except (TypeError, ValueError):
                continue
            p = ev.get("peer")
            if not isinstance(p, dict):
                continue
            if p.get("qualified_years") is not None:
                peer_years = p.get("years")
                peer_qualified_years = p["qualified_years"]
                peer_window = p.get("window")
                break
            if p.get("peer_pct") is not None:
                peer_pct = p["peer_pct"]
                peer_as_of = p.get("as_of")
                break
        stats[code] = {
            "code": code,
            "name": last_obs.name,
            "listed_weeks": len(eps_in),
            "consecutive_weeks": consecutive,
            "latest_sharpe": last_obs.sharpe,
            "last_listed_week": last_week,
            "on_latest_board": code in latest_codes,
            "week_sharpe": dict(eps_in),
            "near_12w_qualified": sum(
                1 for _, o in recent if o.sharpe >= QUALIFIED_SHARPE
            ),
            "near_12w_total": len(recent),
            "peer_pct": peer_pct,
            "peer_as_of": peer_as_of,
            "peer_years": peer_years,
            "peer_qualified_years": peer_qualified_years,
            "peer_window": peer_window,
        }

    # 2) 展示筛选（52 周窗口内统计；下限含等于，R5）
    matched = [
        s for s in stats.values()
        if s["listed_weeks"] >= min_weeks
        and (min_latest_sharpe is None
             or (s["latest_sharpe"] is not None
                 and s["latest_sharpe"] >= min_latest_sharpe))
        and (not latest_only or s["code"] in latest_codes)
    ]

    # 3) 排序：在榜周数降序 → 最近上榜夏普降序 → 代码升序（R3）
    #    窗口外基金的 latest_sharpe 为 None（min_weeks=0 时才可能进 matched），
    #    用 -inf 排末尾，不能对 None 取负号。
    def _sort_key(s):
        sh = s["latest_sharpe"]
        return (-s["listed_weeks"], -sh if sh is not None else float("-inf"), s["code"])

    matched.sort(key=_sort_key)

    # 4) total 在切片前算；items 切片在排序后（contracts 分页不变量）
    total = len(matched)
    offset = (page - 1) * limit
    item_keys = ("code", "name", "listed_weeks", "consecutive_weeks",
                 "latest_sharpe", "last_listed_week", "on_latest_board",
                 "near_12w_qualified", "near_12w_total", "peer_pct", "peer_as_of",
                 "peer_years", "peer_qualified_years", "peer_window")
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

    # 5) 周历：52 周窗口内的周一序列；range 在窗口内再裁起点。
    #    364=52×7 恰为 7 的倍数，range 起点与窗口起点都天然在周一网格上，
    #    不再需要旧 365 天方案那套「对齐回周一」的修补（design §5.0）。
    first_obs_week = min((eps[0][0] for eps in entries.values()), default=None)
    weeks: list[date] = []
    if first_obs_week is not None and first_obs_week <= current:
        range_start = current - timedelta(weeks=_RANGE_WEEKS[range_key] - 1)
        # 两个上界：窗口起点（52 周）与 range 起点；再取首次观测周。
        start = max(window_start, range_start, first_obs_week)
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

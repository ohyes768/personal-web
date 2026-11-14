"""四挡位估值编排服务：组装材料 → 受理入队 → Hermes 逐股估值 → 解析校验 → 落盘。

skill 契约源在 skills 仓库 investment-analysis/stock-four-level-valuation（v1.0.0：单次单股，
四状态 ready/insufficient_data/blocked/not_applicable，仅 ready 有四挡位价格 levels 与非空 valuation；
非 ready 不出任何价格暗示）。后端侧契约摘要见任务 design.md 与
.trellis/spec/backend/dividend-select/backend/valuation-contract.md（复用同一 Runs API 模式）。
批量异步复用 RefreshJobManager（kind='valuation'），运行中可追加入队（与 quality 同一 append 通道），
受 HERMES_MAX_CONCURRENT 全局限并发，逐股完成即落盘并回报进度。
队列操作与 quality 同构：等待项可取消/调序，运行项经 stop_run + get_run 观察到 cancelled 才收尾，
取消后的幂等键带代数后缀避免 Hermes 重放。
"""
from __future__ import annotations

import json
import re
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Callable, Optional
from zoneinfo import ZoneInfo
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from src.api.models import DividendStock
from src.services.hermes_client import HermesConfig, HermesError, HermesRunCancelled, HermesRunFailed
from src.services.hermes_limiter import HermesLimiter
from src.services.quality_service import QueueConflict
from src.services.run_log import STATE_CANCELLED, STATE_COMPLETED, STATE_FAILED, RunLog
from src.services.valuation_version import VERSION_PATTERN, current_valuation_skill_version
from src.utils.atomic_file import atomic_write
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

SKILL_NAME = "stock-four-level-valuation"
VALUATION_FILE = "valuation_reports.json"
LEVEL_KEYS = ("heavy_position", "add_position", "reduce_position", "full_exit")
ANALYSIS_SECTIONS = ("business", "normalization", "dividend", "valuation", "risk")
STATUSES = ("ready", "insufficient_data", "blocked", "not_applicable")
EVIDENCE_KINDS = ("official", "data_platform", "research", "media", "upstream", "input")
CONFIDENCE_LEVELS = ("high", "medium", "low", "unavailable")
# 收尾窗口（dispatch loop 已停、job 未落终态）内受理新任务的最长等待秒数
ADMISSION_WAIT_SECONDS = 10.0
ACTIVE_ITEM_STATES = {"queued", "running", "cancelling"}


def _now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


class ValuationLevel(BaseModel):
    """单个挡位观察点（price 必填正数；pe/pb 选填，来自 skill levels 计算）。"""

    price: float
    pe: Optional[float] = None
    pb: Optional[float] = None

    @field_validator("price")
    @classmethod
    def _price_positive(cls, value: float) -> float:
        if not value > 0:
            raise ValueError(f"挡位价格必须为正数，得到 {value}")
        return value


class ValuationConfidence(BaseModel):
    level: str
    reason: str

    @field_validator("level")
    @classmethod
    def _level_ok(cls, value: str) -> str:
        if value not in CONFIDENCE_LEVELS:
            raise ValueError(f"confidence.level 必须为 {CONFIDENCE_LEVELS}，得到 {value}")
        return value

    @field_validator("reason")
    @classmethod
    def _reason_nonempty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("confidence.reason 不能为空")
        return value


class ValuationReport(BaseModel):
    """单股估值结果（与 skill 输出 17 字段契约对齐）。

    非 ready 时 levels/valuation 归一为 null：skill 侧四点全 null，这里容忍
    levels 为 null 或全 null 项的 dict，统一归一后存储，绝不为非 ready 合成价格。
    """

    schema_version: str
    skill_version: str = Field(pattern=f"^{VERSION_PATTERN}$")
    code: str
    name: str
    currency: str
    as_of: str
    status: str
    levels: Optional[dict[str, Optional[ValuationLevel]]] = None
    valuation: Optional[dict] = None
    evidence: list[dict] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    confidence: ValuationConfidence
    risks: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    summary: str
    analysis: dict[str, str]
    report_md: str

    @field_validator("code", "name", "summary", "report_md")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("code/name/summary/report_md 不能为空")
        return value

    @field_validator("currency")
    @classmethod
    def _currency_cny(cls, value: str) -> str:
        if value != "CNY":
            raise ValueError(f"currency 必须为 CNY，得到 {value}")
        return value

    @field_validator("as_of")
    @classmethod
    def _as_of_format(cls, value: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError(f"as_of 必须为 YYYY-MM-DD，得到 {value}")
        return value

    @field_validator("status")
    @classmethod
    def _status_ok(cls, value: str) -> str:
        if value not in STATUSES:
            raise ValueError(f"status 必须为 {STATUSES}，得到 {value}")
        return value

    @field_validator("evidence")
    @classmethod
    def _evidence_items(cls, value: list[dict]) -> list[dict]:
        ids: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("evidence 每项必须为对象")
            evidence_id = str(item.get("id") or "")
            if not evidence_id:
                raise ValueError("evidence 每项必须有非空 id")
            if evidence_id in ids:
                raise ValueError(f"evidence id 重复: {evidence_id}")
            ids.add(evidence_id)
            if item.get("kind") not in EVIDENCE_KINDS:
                raise ValueError(f"evidence {evidence_id} kind 必须为 {EVIDENCE_KINDS}")
            if "verification" not in item:
                raise ValueError(f"evidence {evidence_id} 缺少 verification")
        return value

    @field_validator("analysis")
    @classmethod
    def _analysis_sections(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != set(ANALYSIS_SECTIONS):
            raise ValueError(f"analysis 必须恰有 {sorted(ANALYSIS_SECTIONS)} 五段")
        for key, text in value.items():
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"analysis.{key} 必须为非空文本")
        return value

    @model_validator(mode="after")
    def _status_shape(self) -> "ValuationReport":
        if self.status == "ready":
            if not self.levels or set(self.levels) != set(LEVEL_KEYS):
                raise ValueError(f"ready 报告 levels 必须恰有 {sorted(LEVEL_KEYS)} 四键")
            prices = []
            for key in LEVEL_KEYS:
                level = self.levels.get(key)
                if level is None or level.price is None:
                    raise ValueError(f"ready 报告 {key} 价格缺失")
                prices.append(level.price)
            if any(b <= a for a, b in zip(prices, prices[1:])):
                raise ValueError(f"ready 四点必须严格递增（重仓<加仓<减仓<全卖），得到 {prices}")
            if not self.valuation:
                raise ValueError("ready 报告 valuation 不能为空")
        else:
            if self.valuation is not None:
                raise ValueError(f"{self.status} 报告 valuation 必须为 null")
            if self.levels and any(level is not None for level in self.levels.values()):
                raise ValueError(f"{self.status} 报告不得携带任何挡位价格（非 ready 四点全 null）")
        return self


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def parse_valuation_output(raw: str, code: str, name: str) -> ValuationReport:
    """解析 run.output：容错剥离 ```json 围栏后 json.loads + pydantic 校验。

    身份校验：输出 code 缺失时回填请求值；输出与请求 code 不一致按解析失败拒绝
    （skill 契约：身份错误停止，不输出伪造公司结果）。
    """
    text = _FENCE_RE.sub("", raw.strip())
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("output 不是合法 JSON")
        data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("output 不是 JSON 对象")
    reported_code = str(data.get("code") or "")
    if reported_code and reported_code != code:
        raise ValueError(f"输出 code {reported_code} 与请求 {code} 不一致，拒绝保存")
    if not reported_code:
        data["code"] = code
    if not data.get("name"):
        data["name"] = name
    return ValuationReport.model_validate(data)


def build_market_snapshot(m120_service, pe_service, code: str) -> dict:
    """采集 admitted 时点的行情快照（realtime/close/pe/pb），缺失一律 null。

    仅作行情参考进入材料，明确标注不得作为定价依据；任一数据源异常都降级为 null，
    不阻塞受理。
    """
    snapshot: dict = {"realtime": None, "close": None, "pe": None, "pb": None}
    try:
        row = (m120_service.read_m120_with_deviation() or {}).get(code) if m120_service else None
        if isinstance(row, dict):
            snapshot["realtime"] = row.get("realtime")
            snapshot["close"] = row.get("close")
    except Exception:
        logger.warning("股票 %s 行情快照读取失败，按缺失处理", code)
    try:
        pe_row = (pe_service.read_pe_data() or {}).get(code) if pe_service else None
        if isinstance(pe_row, dict):
            snapshot["pe"] = pe_row.get("pe")
            snapshot["pb"] = pe_row.get("pb")
    except Exception:
        logger.warning("股票 %s PE/PB 快照读取失败，按缺失处理", code)
    return snapshot


def build_valuation_payload(
    stock: DividendStock,
    quality_record: Optional[dict],
    market_snapshot: Optional[dict],
) -> dict:
    """组装内联材料：财务/行情事实 + 既有评级（可复用不可映射为价格）。"""
    payload: dict = {
        "code": stock.code,
        "name": stock.name,
        "sw_level1": stock.sw_level1,
        "yield_2023": stock.yield_2023,
        "yield_2024": stock.yield_2024,
        "yield_2025": stock.yield_2025,
        "avg_yield_3y": stock.avg_yield_3y,
        "dividend_2025": stock.dividend_2025,
        "payout_ratio": stock.payout_ratio,
        "roe": stock.roe,
        "roe_year": stock.roe_year,
        "roe_avg_3y": stock.roe_avg_3y,
        "annual_net_profit_ex_non_recurring": stock.annual_net_profit_ex_non_recurring,
        "annual_profit_year": stock.annual_profit_year,
        "net_profit_ex_non_recurring_yoy": stock.net_profit_ex_non_recurring_yoy,
        "net_profit_cagr_3y": stock.net_profit_cagr_3y,
        "debt_asset_ratio": stock.debt_asset_ratio,
        "gross_profit_margin": stock.gross_profit_margin,
        "eps": stock.eps,
        "eps_year": stock.eps_year,
        "market_snapshot": {"realtime": None, "close": None, "pe": None, "pb": None,
                            **(market_snapshot or {}),
                            "note": "现价仅行情参考，不得按现价比例推导四点"},
    }
    if quality_record:
        payload["existing_quality_rating"] = {
            "skill": "basic-quality-rating",
            "skill_version": quality_record.get("skill_version"),
            "scored_at": quality_record.get("scored_at"),
            "data_date": quality_record.get("data_date"),
            "dimensions": quality_record.get("dimensions"),
            "summary": quality_record.get("summary"),
            "report_md": quality_record.get("report_md"),
            "note": "复用业务/护城河/管理层/行业证据与风险；分数不是估值参数",
        }
    return payload


def build_prompt(payload: dict, skill_version: str | None = None, data_date: str = "") -> str:
    """点名 skill + 内联材料 JSON + 输出约束（bare JSON、版本 provenance）。"""
    data = json.dumps(payload, ensure_ascii=False)
    return (
        f"请使用 {SKILL_NAME} skill 对以下单只 A 股做四挡位估值（重仓/加仓/减仓/全卖价格观察线）。\n"
        f"数据截止日按 {data_date} 使用；材料不足时按 skill 规则做最多两轮定向补查，仍缺则收口为"
        " insufficient_data，不要继续无限搜索。\n"
        "下方 JSON 为调用方内联材料（财务/行情事实与既有基本面评级）：登记证据时 origin 用 "
        "inline:<日期>:<简短描述>；既有评级只可复用证据与风险，不得把评分或星级映射为价格；"
        "现价仅行情参考，禁止以现价比例推导四个价格点。\n"
        "严格按 skill 流程完成 finalize 与 check，最终回复只输出一个完整 JSON 对象（17 字段、含 "
        "report_md），不要 markdown 代码围栏，不要任何解释文字。\n"
        "输出 skill_version，必须来自本次实际执行 skill 的 metadata.version，不得猜测或回填。\n"
        + (f"本次要求已部署 skill 版本 {skill_version}；版本不符则报告失败，不要冒充该版本。\n" if skill_version else "")
        + f"内联材料：{data}"
    )


class ValuationService:
    """估值编排：入口校验 → 受理入队（运行中可追加）→ FIFO 逐股分析 → 落盘。

    逐股实时状态（queued/running/completed/failed）保存在内存 items，供前端展示；
    受理时快照 payload 与 data_date（幂等键逐项），排队期间数据变化不影响已受理项。
    服务重启后清空（job 置 interrupted，语义一致），已落盘报告保留。
    最近一次尝试的终态（含失败的 run_id）另存台账文件，重启后失败行仍可下载会话记录。
    """

    def __init__(self, reports_path: Path, limiter: HermesLimiter | None = None):
        self.reports_path = reports_path
        # 跨 service 全局限流（quality + valuation 合计 ≤ HERMES_MAX_CONCURRENT）；
        # None = 不参与全局限流（测试用），本地 limit 仍然生效
        self._limiter = limiter
        self._file_lock = threading.RLock()
        self._cond = threading.Condition(threading.RLock())
        self._items: dict[str, dict] = {}
        self._pending: deque[str] = deque()
        self._running = 0
        self._active_job_id: Optional[str] = None
        self._accepting = False
        self._cancel_generations = self._load_generations()
        # 最近一次分析尝试台账：失败也留 run_id，界面才能下载失败那次的会话记录
        self._run_log = RunLog(self._run_log_path())

    # ---- 逐股状态 ----

    def _run_log_path(self) -> Path:
        return self.reports_path.with_name("valuation_run_log.json")

    def get_per_code(self) -> dict:
        # 台账有自己的锁：先读出来，别占着 _cond（调度线程频繁取它）
        failed = self._run_log.failed_entries()
        with self._cond:
            positions = {code: index + 1 for index, code in enumerate(self._pending)}
            result = {code: {
                "state": item.get("state"),
                "error": item.get("error"),
                "updated_at": item.get("updated_at"),
                "name": item.get("name"),
                "queued_at": item.get("queued_at"),
                "started_at": item.get("started_at"),
                "finished_at": item.get("finished_at"),
                "item_id": item.get("attempt_id"),
                "position": positions.get(code),
                "run_id": item.get("run_id"),
            } for code, item in self._items.items()}
            # 服务重启后内存队列清空：把台账里最近一次失败的记录并回来，
            # 失败行才能继续下载那次的会话记录（run_id 来自台账，不来自内存）。
            for code, entry in failed.items():
                if code in result:
                    continue
                result[code] = {
                    "state": STATE_FAILED,
                    "error": entry.get("error"),
                    "updated_at": entry.get("updated_at"),
                    "name": entry.get("name"),
                    "queued_at": entry.get("queued_at"),
                    "started_at": entry.get("started_at"),
                    "finished_at": entry.get("finished_at"),
                    "item_id": None,
                    "position": None,
                    "run_id": entry.get("run_id"),
                }
            return result

    def queue_snapshot(self) -> dict:
        per_code = self.get_per_code()
        return {
            "per_code": per_code,
            "running_count": sum(1 for item in per_code.values() if item.get("state") in ("running", "cancelling")),
            "queued_count": sum(1 for item in per_code.values() if item.get("state") == "queued"),
        }

    # ---- 落盘读写 ----

    def _read_all(self) -> dict:
        try:
            return json.loads(self.reports_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_one(self, report: ValuationReport, data_date: str, analysis_duration_seconds: float,
                  run_id: str | None = None) -> None:
        evaluated_at = _now()
        record = {**report.model_dump(), "evaluated_at": evaluated_at, "data_date": data_date,
                  "analysis_duration_seconds": analysis_duration_seconds, "run_id": run_id}
        with self._file_lock:
            merged = self._read_all()
            merged[report.code] = record
            encoded = json.dumps(merged, ensure_ascii=False, allow_nan=False)
            atomic_write(self.reports_path, lambda p: p.write_text(encoded, encoding="utf-8"))

    def get_all(self) -> dict:
        with self._file_lock:
            return self._read_all()

    # ---- 取消代数（幂等键防重放） ----

    def _generations_path(self) -> Path:
        return self.reports_path.with_name("valuation_cancel_generations.json")

    def _load_generations(self) -> dict[str, int]:
        try:
            data = json.loads(self._generations_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): int(v) for k, v in data.items() if isinstance(v, int) and v >= 0}

    def _store_generation(self, code: str, generation: int) -> None:
        """确认取消后，下一次受理改用新的幂等键，避免 Hermes 重放已取消的 run。"""
        with self._file_lock:
            self._cancel_generations[code] = generation
            encoded = json.dumps(self._cancel_generations, ensure_ascii=False)
            atomic_write(self._generations_path(), lambda path: path.write_text(encoded, encoding="utf-8"))

    # ---- 受理与调度 ----

    def _idempotency_key(self, item: dict) -> str:
        version_key = item["skill_version"] or f"unknown-{item['attempt_id']}"
        base = f"valuation-{item['code']}-{item['data_date']}-{version_key}"
        generation = int(item.get("cancel_generation") or 0)
        return base if generation <= 0 else f"{base}-c{generation}"

    def _admit(self, ordered: list[str], snapshots: dict[str, dict]) -> None:
        """建队列项并入队（调用方持有 _cond）。"""
        for code in ordered:
            snap = snapshots[code]
            self._items[code] = {
                "code": code, "name": snap["name"], "state": "queued", "error": None,
                "queued_at": _now(), "started_at": None, "finished_at": None, "updated_at": _now(),
                "data_date": snap["data_date"], "payload": snap["payload"],
                "skill_version": snap["skill_version"], "attempt_id": uuid4().hex,
                "cancel_generation": int(self._cancel_generations.get(code, 0)),
                "cancel_requested": False, "cancel_event": threading.Event(),
                "run_id": None, "stop_sent": False,
            }
            self._pending.append(code)

    def _wait_for_terminal(self, refresh_jobs) -> None:
        """任务收尾窗口（dispatch loop 已停、job 未落终态）内等它结束再受理新任务。"""
        deadline = monotonic() + ADMISSION_WAIT_SECONDS
        while refresh_jobs.active("valuation") is not None:
            if monotonic() > deadline:
                raise ValueError("上一个估值任务收尾中，请稍后重试")
            self._cond.wait(0.05)

    def submit_valuation(
        self,
        codes: list[str],
        hermes_config: HermesConfig,
        stocks: dict[str, DividendStock],
        data_date: str,
        refresh_jobs,
        quality_scores: dict,
        submit_run_fn: Callable[[HermesConfig, str, str], str],
        poll_run_fn: Callable[[HermesConfig, str], str],
        market_snapshot_fn: Callable[[str], dict] | None = None,
        stop_run_fn: Optional[Callable[[HermesConfig, str], str]] = None,
        get_run_fn: Optional[Callable[[HermesConfig, str], dict]] = None,
    ) -> Optional[dict]:
        """受理批量估值；返回 job dict（含 reused）或 None（服务关闭中）。

        无任务时开新任务；任务运行中把新代码追加进当前任务（reused=true），已在
        排队/运行/取消中的代码幂等跳过且不重置时间戳。未配置、股票不在采集池或收尾等待
        超时时抛 ValueError。
        """
        if not hermes_config.is_configured:
            raise ValueError("Hermes 未配置")
        missing = [code for code in codes if code not in stocks]
        if missing:
            raise ValueError(f"以下股票不在采集池：{','.join(missing)}")
        ordered = list(dict.fromkeys(codes))
        skill_version = current_valuation_skill_version()
        snapshots = {}
        for code in ordered:
            snapshot = market_snapshot_fn(code) if market_snapshot_fn else None
            snapshots[code] = {
                "name": stocks[code].name,
                "data_date": data_date,
                "skill_version": skill_version,
                "payload": build_valuation_payload(stocks[code], quality_scores.get(code), snapshot),
            }

        def work(progress: Callable[..., None]) -> None:
            limit = max(1, hermes_config.max_concurrent)
            limiter = self._limiter
            with self._cond:
                self._cond.notify_all()
            while True:
                with self._cond:
                    while self._running >= limit or not self._pending:
                        if not self._pending and self._running == 0:
                            self._accepting = False
                            self._active_job_id = None
                            return
                        self._cond.wait()
                    code = self._pending.popleft()
                    item = self._items.get(code)
                    if not item or item.get("state") != "queued":
                        continue
                    # 放回队首，锁外等共享全局名额；等待期间项保持 queued（可取消/调序）
                    self._pending.appendleft(code)
                holds_slot = False
                while True:
                    with self._cond:
                        item = self._items.get(code)
                        if not item or item.get("state") != "queued" or code not in self._pending:
                            break
                    if limiter is None or limiter.acquire(timeout=0.2):
                        holds_slot = True
                        break
                with self._cond:
                    item = self._items.get(code)
                    if not holds_slot or not item or item.get("state") != "queued" or code not in self._pending:
                        if holds_slot:
                            limiter.release()
                        continue  # 等待期间被取消/移除：回调度循环，不消耗名额
                    self._pending.remove(code)
                    started_at = _now()
                    item.update(state="running", started_at=started_at, updated_at=started_at, error=None)
                    self._running += 1
                threading.Thread(
                    target=self._run_one, daemon=True,
                    args=(code, hermes_config, submit_run_fn, poll_run_fn, progress,
                          stop_run_fn, get_run_fn, holds_slot),
                ).start()

        with self._cond:
            if self._accepting and self._active_job_id:
                fresh = [code for code in ordered
                         if (self._items.get(code) or {}).get("state") not in ACTIVE_ITEM_STATES]
                if not fresh:
                    job = refresh_jobs.get(self._active_job_id)
                    if job:
                        return {**job, "reused": True}
                else:
                    self._admit(fresh, snapshots)
                    updated = refresh_jobs.append_codes(self._active_job_id, fresh)
                    if updated is not None:
                        self._cond.notify_all()
                        return {**updated, "reused": True}
                    # job 恰在收尾窗口变终态，或服务已停止受理：撤回刚入队的项
                    for code in fresh:
                        self._pending.remove(code)
                        self._items.pop(code, None)
                    if not refresh_jobs.admission_open():
                        return None
            self._wait_for_terminal(refresh_jobs)
            self._admit(ordered, snapshots)
            job = refresh_jobs.submit("valuation", ordered, work, params={"data_date": data_date})
            if job is None or job.get("reused"):
                for code in ordered:
                    self._pending.remove(code)
                    self._items.pop(code, None)
                if job is None:
                    return None
                raise ValueError("已有估值任务在跑，请稍后重试")
            self._active_job_id = job["job_id"]
            self._accepting = True
            return job

    def _find_item(self, item_id: str):
        for code, item in self._items.items():
            if item.get("attempt_id") == item_id:
                return code, item
        return None

    def cancel_item(self, item_id: str, refresh_jobs) -> dict:
        """取消这一次估值。等待项在提交 Hermes 前移除；运行项只记下意图。

        重复取消同一身份是幂等的。过期身份或已结束的估值抛 QueueConflict。
        """
        with self._cond:
            found = self._find_item(item_id)
            if found is None:
                raise QueueConflict("该任务已不存在或不是当前这一次估值")
            code, item = found
            state = item.get("state")
            if state in ("cancelled", "cancelling"):
                return self.queue_snapshot()
            if state == "queued":
                if code not in self._pending or not self._active_job_id:
                    raise QueueConflict("该任务已不在等待队列")
                index = list(self._pending).index(code)
                previous = (item.get("finished_at"), item.get("updated_at"), item.get("error"))
                finished = _now()
                item.update(state="cancelled", error=None, finished_at=finished, updated_at=finished)
                try:
                    saved = refresh_jobs.note_queue_cancel(
                        self._active_job_id, code, list(self._pending), kind='valuation')
                except Exception:
                    self._pending.insert(index, code)
                    item.update(state="queued", finished_at=previous[0], updated_at=previous[1], error=previous[2])
                    raise
                if saved is None:
                    self._pending.insert(index, code)
                    item.update(state="queued", finished_at=previous[0], updated_at=previous[1], error=previous[2])
                    raise QueueConflict("该任务已不在等待队列")
                self._cond.notify_all()
                return self.queue_snapshot()
            if state == "running":
                item["cancel_requested"] = True
                item["state"] = "cancelling"
                item["updated_at"] = _now()
                event = item.get("cancel_event")
                if event is not None:
                    event.set()
                self._cond.notify_all()
                return self.queue_snapshot()
            raise QueueConflict("该次估值已结束")

    def move_item(self, item_id: str, action: str, refresh_jobs) -> dict:
        """只调整仍在等待的项。时间戳不变，顺序先落盘再返回。"""
        if action not in ("front", "up", "down"):
            raise ValueError("不支持的调序动作")
        with self._cond:
            found = self._find_item(item_id)
            if found is None:
                raise QueueConflict("该任务已不存在或不是当前这一次估值")
            code, item = found
            if item.get("state") != "queued" or code not in self._pending:
                raise QueueConflict("任务已开始执行，无法调整排队顺序")
            order = list(self._pending)
            index = order.index(code)
            if action in ("front", "up") and index == 0:
                raise QueueConflict("已在队首")
            if action == "down" and index == len(order) - 1:
                raise QueueConflict("已在队尾")
            if action == "front":
                order.insert(0, order.pop(index))
            elif action == "up":
                order[index - 1], order[index] = order[index], order[index - 1]
            else:
                order[index + 1], order[index] = order[index], order[index + 1]
            previous = list(self._pending)
            self._pending = deque(order)
            try:
                saved = (refresh_jobs.note_queue_order(self._active_job_id, order, kind='valuation')
                         if self._active_job_id else None)
            except Exception:
                self._pending = deque(previous)
                raise
            if saved is None:
                self._pending = deque(previous)
                raise QueueConflict("任务已结束")
            return self.queue_snapshot()

    def _wait_item(self, item: dict, hermes_config: HermesConfig) -> None:
        interval = hermes_config.poll_interval if hermes_config.poll_interval > 0 else 0.05
        event = item.get("cancel_event")
        if event is None:
            threading.Event().wait(interval)
            return
        event.wait(interval)
        event.clear()

    def _run_one(self, code, hermes_config, submit_run_fn, poll_run_fn, progress, stop_run_fn, get_run_fn,
                 holds_slot: bool = False) -> None:
        item = self._items[code]
        try:
            try:
                kind, report, error, duration, bump = self._execute(
                    item, hermes_config, submit_run_fn, poll_run_fn, stop_run_fn, get_run_fn)
            except Exception as exc:  # 未预期异常按该股失败计，避免 _running 不归零
                logger.exception("股票 %s 估值过程异常", code)
                kind, report, error, duration, bump = "failed", None, f"估值过程异常: {exc}"[:300], None, False
            if kind == "completed" and report is not None:
                try:
                    self._save_one(report, item["data_date"], duration if duration is not None else 0.0,
                                   run_id=item.get("run_id"))
                except (OSError, ValueError) as exc:
                    logger.exception("估值结果落盘失败 %s", code)
                    kind, error, bump = "failed", f"估值结果保存失败: {exc}", False
            if kind == "cancelled" and bump:
                try:
                    self._store_generation(code, int(item.get("cancel_generation") or 0) + 1)
                except OSError:
                    logger.exception("取消后的幂等代数未能落盘 %s", code)
            self._record_attempt(code, item, kind, error)
            self._finish_item(code, item, kind, error, progress)
        finally:
            if holds_slot:
                self._limiter.release()

    def _record_attempt(self, code: str, item: dict, kind: str, error: str | None) -> None:
        """把这一次尝试的终态写进台账：失败也留 run_id，界面才能下载会话记录。"""
        state = {STATE_COMPLETED: STATE_COMPLETED, STATE_CANCELLED: STATE_CANCELLED}.get(kind, STATE_FAILED)
        self._run_log.record(
            code,
            state=state,
            run_id=item.get("run_id"),
            name=item.get("name"),
            error=error if state == STATE_FAILED else None,
            attempt_id=item.get("attempt_id"),
            queued_at=item.get("queued_at"),
            started_at=item.get("started_at"),
            finished_at=_now(),
        )

    def _execute(self, item, hermes_config, submit_run_fn, poll_run_fn, stop_run_fn, get_run_fn):
        with self._cond:
            cancel_before_submit = bool(item.get("cancel_requested"))
        if cancel_before_submit:
            return "cancelled", None, "", None, False
        started = monotonic()
        expected_version = item["skill_version"]
        prompt = build_prompt(item["payload"], expected_version, item["data_date"])
        try:
            run_id = submit_run_fn(hermes_config, prompt, self._idempotency_key(item))
        except HermesError as exc:
            return "failed", None, str(exc)[:300], None, False
        with self._cond:
            if item.get("attempt_id"):
                item["run_id"] = run_id
            want_stop = bool(item.get("cancel_requested"))
        if get_run_fn is not None:
            return self._watch(item, hermes_config, run_id, started, expected_version, stop_run_fn, get_run_fn, want_stop)
        if want_stop and stop_run_fn is not None:
            self._send_stop(item, hermes_config, run_id, stop_run_fn)
        try:
            output = poll_run_fn(hermes_config, run_id)
        except HermesRunCancelled:
            return "cancelled", None, "", None, True
        except HermesRunFailed as exc:
            return "failed", None, str(exc)[:300], None, False
        except HermesError as exc:
            return "failed", None, str(exc)[:300], None, False
        return self._accept_output(item, output, expected_version, started)

    def _watch(self, item, hermes_config, run_id, started, expected_version, stop_run_fn, get_run_fn, want_stop):
        deadline = monotonic() + hermes_config.timeout
        if want_stop and stop_run_fn is not None:
            self._send_stop(item, hermes_config, run_id, stop_run_fn)
        while True:
            with self._cond:
                cancelling = bool(item.get("cancel_requested"))
                stop_sent = bool(item.get("stop_sent"))
            if cancelling and not stop_sent and stop_run_fn is not None:
                self._send_stop(item, hermes_config, run_id, stop_run_fn)
            try:
                data = get_run_fn(hermes_config, run_id)
            except HermesError as exc:
                if cancelling:
                    with self._cond:
                        item["error"] = f"取消结果未确认: {exc}"[:300]
                        item["updated_at"] = _now()
                    self._wait_item(item, hermes_config)
                    continue
                return "failed", None, str(exc)[:300], None, False
            status = str((data or {}).get("status") or "")
            if status == "completed":
                return self._accept_output(item, str(data.get("output") or ""), expected_version, started)
            if status == "cancelled":
                return "cancelled", None, "", None, True
            if status in ("failed", "interrupted"):
                return "failed", None, f"run {run_id} 终态 {status}", None, False
            if not cancelling and monotonic() >= deadline:
                return "failed", None, f"run {run_id} 超过 {hermes_config.timeout}s 未完成（最后状态 {status or 'unknown'}）", None, False
            self._wait_item(item, hermes_config)

    def _send_stop(self, item, hermes_config, run_id, stop_run_fn) -> None:
        try:
            status = str(stop_run_fn(hermes_config, run_id) or "")
        except HermesError as exc:
            with self._cond:
                item["error"] = f"取消请求失败: {exc}"[:300]
                item["updated_at"] = _now()
            return
        # stopping 只表示已受理；cancelled 仍要等随后的查询确认。其它响应不算成功。
        if status not in {"stopping", "cancelled"}:
            with self._cond:
                item["error"] = f"取消请求失败: 未确认受理（{status or '未知'}）"[:300]
                item["updated_at"] = _now()
            return
        with self._cond:
            item["stop_sent"] = True
            if item.get("error") and str(item.get("error")).startswith("取消请求失败"):
                item["error"] = None

    def _accept_output(self, item, output: str, expected_version, started):
        duration = round(monotonic() - started, 3)
        if not output:
            return "failed", None, "output 为空", None, False
        try:
            report = parse_valuation_output(output, item["code"], item["name"])
            if expected_version and report.skill_version != expected_version:
                raise ValueError(f"skill 版本不符：要求 {expected_version}，实际 {report.skill_version or '未知'}，请检查 Hermes 部署")
        except ValueError as exc:
            text = str(exc)
            prefix = "" if text.startswith("skill 版本不符") or text.startswith("解析失败") else "解析失败: "
            return "failed", None, f"{prefix}{text}"[:300], None, False
        return "completed", report, "", duration, False

    def _finish_item(self, code, item, kind, error, progress) -> None:
        # 先结清进度再归还名额，调度循环才不会在计数写入前把任务收成终态。
        try:
            if kind == "cancelled":
                progress(code, False, outcome="cancelled")
            else:
                if kind != "completed":
                    logger.warning("股票 %s 估值失败: %s", code, error)
                progress(code, kind == "completed")
        finally:
            finished = _now()
            with self._cond:
                if self._items.get(code) is item:
                    item.update(
                        state={"completed": "completed", "cancelled": "cancelled"}.get(kind, "failed"),
                        error=None if kind in ("completed", "cancelled") else error,
                        finished_at=finished, updated_at=finished,
                    )
                self._running -= 1
                self._cond.notify_all()

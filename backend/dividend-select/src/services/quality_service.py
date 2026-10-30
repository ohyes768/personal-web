"""基本面评级编排服务：组装数据 → 受理入队 → Hermes 逐股分析 → 解析校验 → 落盘。

评分契约源在 skills 仓库 finance-macro/basic-quality-rating（v3 起：证据不足的维度为 null，
任一维 null 时 weighted_score/stars/boundary 全为 null，即「未评级」）；后端侧契约摘要见
.trellis/spec/backend/dividend-select/backend/quality-rating-contract.md。
批量异步复用 RefreshJobManager（kind='quality'）。任务运行中可继续受理新代码：追加进当前
任务的 FIFO 队列（重复提交幂等去重），受 HERMES_MAX_CONCURRENT 全局限并发，逐股完成即落盘
并回报进度。受理与调度结束判定共用同一把锁，追加不会在任务收尾窗口丢失。
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
from src.services.quality_version import VERSION_PATTERN, current_quality_skill_version
from src.utils.atomic_file import atomic_write
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

SKILL_NAME = "basic-quality-rating"
QUALITY_FILE = "quality_scores.json"
DIMENSION_WEIGHTS = {"business": 0.25, "moat": 0.25, "industry": 0.20, "management": 0.15, "financial": 0.15}
SCORE_TOLERANCE = 0.01
# 收尾窗口（dispatch loop 已停、job 未落终态）内受理新任务的最长等待秒数
ADMISSION_WAIT_SECONDS = 10.0
ACTIVE_ITEM_STATES = {"queued", "running", "cancelling"}


class QueueConflict(Exception):
    """调序或取消与这一次分析的实际状态不一致。调用方应返回当前快照。"""


def _now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def _stars_for(score: float) -> int:
    """加权总分 → 星级（与 SKILL.md 映射表逐字一致）。"""
    if score >= 4.5:
        return 5
    if score >= 4.0:
        return 4
    if score >= 3.0:
        return 3
    if score >= 2.0:
        return 2
    return 1


class QualityScore(BaseModel):
    """单股评级结果（与 skill 输出 JSON 契约对齐）。"""

    code: str
    name: str
    skill_version: Optional[str] = Field(default=None, pattern=f"^{VERSION_PATTERN}$")
    dimensions: dict[str, Optional[int]]
    weighted_score: Optional[float]
    stars: Optional[int]
    boundary: Optional[str] = None
    summary: str
    risks: list[str] = Field(default_factory=list)
    watch_points: list[str] = Field(default_factory=list)
    report_md: str

    @field_validator("dimensions")
    @classmethod
    def _dimensions_ok(cls, value: dict[str, Optional[int]]) -> dict[str, Optional[int]]:
        if set(value) != set(DIMENSION_WEIGHTS):
            raise ValueError(f"dimensions 键必须为 {sorted(DIMENSION_WEIGHTS)}")
        for key, score in value.items():
            if score is None:
                continue
            if not isinstance(score, int) or not 1 <= score <= 5:
                raise ValueError(f"维度 {key} 分数须为 1-5 整数或 null，得到 {score}")
        return value

    @model_validator(mode="after")
    def _score_and_stars_consistent(self) -> "QualityScore":
        unrated = any(score is None for score in self.dimensions.values())
        if unrated:
            # v3 契约：任一维未评分即为「未评级」，三个派生字段全 null，禁止回填或按剩余权重折算
            if any(v is not None for v in (self.weighted_score, self.stars, self.boundary)):
                raise ValueError("存在未评分维度时 weighted_score/stars/boundary 必须全为 null")
        else:
            if self.weighted_score is None or self.stars is None:
                raise ValueError("五维齐全时 weighted_score/stars 不能为 null")
            expected = round(sum(self.dimensions[k] * w for k, w in DIMENSION_WEIGHTS.items()), 2)
            if abs(self.weighted_score - expected) > SCORE_TOLERANCE:
                raise ValueError(f"weighted_score {self.weighted_score} 与加权和 {expected} 不符")
            expected_stars = _stars_for(self.weighted_score)
            if self.stars != expected_stars:
                raise ValueError(f"stars {self.stars} 与映射不符（{self.weighted_score} 应为 {expected_stars} 星）")
        if not self.report_md or not self.report_md.strip():
            raise ValueError("report_md 不能为空")
        return self


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def parse_quality_output(raw: str, code: str, name: str) -> QualityScore:
    """解析 run.output：容错剥离 ```json 围栏后 json.loads + pydantic 校验。"""
    text = _FENCE_RE.sub("", raw.strip())
    # 输出偶发前后缀杂文时，截取首个 { 到末个 } 之间再试一次
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("output 不是合法 JSON")
        data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("output 不是 JSON 对象")
    if not data.get("code"):
        data["code"] = code
    if not data.get("name"):
        data["name"] = name
    return QualityScore.model_validate(data)


def build_stock_payload(stock: DividendStock) -> dict:
    """挑参与评分的字段组装 JSON（缺失传 null，由 skill 按可评分性规则处理）。"""
    return {
        "code": stock.code,
        "name": stock.name,
        "sw_level1": stock.sw_level1,
        "sw_level2": stock.sw_level2,
        "yield_2023": stock.yield_2023,
        "yield_2024": stock.yield_2024,
        "yield_2025": stock.yield_2025,
        "avg_yield_3y": stock.avg_yield_3y,
        "dividend_count_2023": stock.dividend_count_2023,
        "dividend_count_2024": stock.dividend_count_2024,
        "dividend_count_2025": stock.dividend_count_2025,
        "payout_ratio": stock.payout_ratio,
        "roe": stock.roe,
        "roe_year": stock.roe_year,
        "roe_avg_3y": stock.roe_avg_3y,
        "roe_history": [{"year": item.year, "value": item.value} for item in stock.roe_history],
        "annual_net_profit_ex_non_recurring": stock.annual_net_profit_ex_non_recurring,
        "annual_profit_year": stock.annual_profit_year,
        "net_profit_ex_non_recurring_yoy": stock.net_profit_ex_non_recurring_yoy,
        "net_profit_cagr_3y": stock.net_profit_cagr_3y,
        "previous_quarter_yoy_pct": stock.previous_quarter_yoy_pct,
        "previous_quarter_label": stock.previous_quarter_label,
        "latest_quarter_yoy_pct": stock.latest_quarter_yoy_pct,
        "latest_quarter_label": stock.latest_quarter_label,
        "debt_asset_ratio": stock.debt_asset_ratio,
        "gross_profit_margin": stock.gross_profit_margin,
        "shareholder_count": stock.shareholder_count,
        "shareholder_change_pct": stock.shareholder_change_pct,
        "eps": stock.eps,
        "eps_year": stock.eps_year,
    }


def build_prompt(payload: dict, skill_version: str | None = None) -> str:
    """点名 skill + 数据 JSON + 输出约束。"""
    data = json.dumps(payload, ensure_ascii=False)
    return (
        f"请使用 {SKILL_NAME} skill 评估以下股票，严格按 skill 的五维细则与星级映射打分。\n"
        f"最终回复只输出一个 JSON 对象（含 report_md），不要 markdown 代码围栏，不要任何解释文字。\n"
        "输出 skill_version，必须来自本次实际执行 skill 的 metadata.version，不得猜测或回填。\n"
        + (f"本次要求已部署 skill 版本 {skill_version}；版本不符则报告失败，不要冒充该版本。\n" if skill_version else "")
        + f"股票数据：{data}"
    )


class QualityService:
    """评级编排：入口校验 → 受理入队（运行中可追加）→ FIFO 逐股分析 → 落盘。

    逐股实时状态（queued/running/completed/failed + 受理/开始/结束时间）保存在内存
    items，供前端队列面板与列表行内展示；受理时快照 payload 与 data_date（幂等键逐项），
    排队期间数据变化不影响已受理项。服务重启后清空（job 置 interrupted，语义一致）。
    """

    def __init__(self, quality_path: Path):
        self.quality_path = quality_path
        self._file_lock = threading.RLock()
        self._cond = threading.Condition(threading.RLock())
        self._items: dict[str, dict] = {}
        self._pending: deque[str] = deque()
        self._running = 0
        self._active_job_id: Optional[str] = None
        self._accepting = False
        self._progress: Optional[Callable] = None
        self._cancel_generations = self._load_generations()

    # ---- 逐股状态 ----

    def get_per_code(self) -> dict:
        with self._cond:
            positions = {code: index + 1 for index, code in enumerate(self._pending)}
            return {code: {
                "state": item.get("state"),
                "error": item.get("error"),
                "updated_at": item.get("updated_at"),
                "name": item.get("name"),
                "queued_at": item.get("queued_at"),
                "started_at": item.get("started_at"),
                "finished_at": item.get("finished_at"),
                "item_id": item.get("attempt_id"),
                "position": positions.get(code),
            } for code, item in self._items.items()}

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
            return json.loads(self.quality_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_one(self, score: QualityScore, data_date: str, analysis_duration_seconds: float) -> None:
        scored_at = _now()
        record = {**score.model_dump(), "scored_at": scored_at, "data_date": data_date,
                  "analysis_duration_seconds": analysis_duration_seconds}
        with self._file_lock:
            merged = self._read_all()
            merged[score.code] = record
            encoded = json.dumps(merged, ensure_ascii=False, allow_nan=False)
            atomic_write(self.quality_path, lambda p: p.write_text(encoded, encoding="utf-8"))

    def get_all(self) -> dict:
        with self._file_lock:
            return self._read_all()

    # ---- 受理与调度 ----

    def _generations_path(self) -> Path:
        return self.quality_path.with_name("quality_cancel_generations.json")

    def _load_generations(self) -> dict[str, int]:
        try:
            data = json.loads(self._generations_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        loaded = {}
        for code, value in data.items():
            if isinstance(value, int) and value >= 0:
                loaded[str(code)] = value
        return loaded

    def _store_generation(self, code: str, generation: int) -> None:
        """确认取消后，下一次受理改用新的幂等键，避免 Hermes 重放已取消的 run。"""
        with self._file_lock:
            self._cancel_generations[code] = generation
            encoded = json.dumps(self._cancel_generations, ensure_ascii=False)
            atomic_write(self._generations_path(), lambda path: path.write_text(encoded, encoding="utf-8"))

    def _idempotency_key(self, item: dict) -> str:
        version_key = item["skill_version"] or f"unknown-{item['attempt_id']}"
        base = f"quality-{item['code']}-{item['data_date']}-{version_key}"
        generation = int(item.get("cancel_generation") or 0)
        return base if generation <= 0 else f"{base}-c{generation}"

    def _admit(self, ordered: list[str], snapshots: dict[str, dict]) -> None:
        """建队列项并入队（调用方持有 _cond）。重复受理的旧项由调用方处理。"""
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
        while refresh_jobs.active("quality") is not None:
            if monotonic() > deadline:
                raise ValueError("上一个评级任务收尾中，请稍后重试")
            self._cond.wait(0.05)

    def submit_analysis(
        self,
        codes: list[str],
        hermes_config: HermesConfig,
        stocks: dict[str, DividendStock],
        data_date: str,
        refresh_jobs,
        submit_run_fn: Callable[[HermesConfig, str, str], str],
        poll_run_fn: Callable[[HermesConfig, str], str],
        stop_run_fn: Optional[Callable[[HermesConfig, str], str]] = None,
        get_run_fn: Optional[Callable[[HermesConfig, str], dict]] = None,
    ) -> Optional[dict]:
        """受理批量评级；返回 job dict（含 reused）或 None（服务关闭中）。

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
        skill_version = current_quality_skill_version()
        snapshots = {code: {"name": stocks[code].name, "data_date": data_date,
                            "skill_version": skill_version,
                            "payload": build_stock_payload(stocks[code])}
                     for code in ordered}

        def work(progress: Callable[..., None]) -> None:
            limit = max(1, hermes_config.max_concurrent)
            with self._cond:
                self._progress = progress
                self._cond.notify_all()
            while True:
                with self._cond:
                    while self._running >= limit or not self._pending:
                        if not self._pending and self._running == 0:
                            # 队列清空且无在跑项：此后受理一律开新任务。
                            # 退出判定与追加、取消、调序共用 _cond。
                            self._accepting = False
                            self._active_job_id = None
                            self._progress = None
                            return
                        self._cond.wait()
                    code = self._pending.popleft()
                    item = self._items.get(code)
                    if not item or item.get("state") != "queued":
                        continue
                    started_at = _now()
                    item.update(state="running", started_at=started_at, updated_at=started_at, error=None)
                    self._running += 1
                threading.Thread(
                    target=self._run_one, daemon=True,
                    args=(code, hermes_config, submit_run_fn, poll_run_fn, progress, stop_run_fn, get_run_fn),
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
                        return {**updated, "reused": True}
                    # job 恰在收尾窗口变终态，或服务已停止受理：撤回刚入队的项
                    for code in fresh:
                        self._pending.remove(code)
                        self._items.pop(code, None)
                    if not refresh_jobs.admission_open():
                        return None
            self._wait_for_terminal(refresh_jobs)
            self._admit(ordered, snapshots)
            job = refresh_jobs.submit("quality", ordered, work, params={"data_date": data_date})
            if job is None or job.get("reused"):
                # closing 或（防御性）出现竞态活跃任务：撤回本次受理，不留幽灵队列项
                for code in ordered:
                    self._pending.remove(code)
                    self._items.pop(code, None)
                if job is None:
                    return None
                raise ValueError("已有评级任务在跑，请稍后重试")
            self._active_job_id = job["job_id"]
            self._accepting = True
            return job

    def _find_item(self, item_id: str):
        for code, item in self._items.items():
            if item.get("attempt_id") == item_id:
                return code, item
        return None

    def cancel_item(self, item_id: str, refresh_jobs) -> dict:
        """按这一次分析的身份取消。等待项在提交 Hermes 前移除；运行项只记下意图。

        重复取消同一身份是幂等的。过期身份或已结束的分析抛 QueueConflict。
        """
        with self._cond:
            found = self._find_item(item_id)
            if found is None:
                raise QueueConflict("该任务已不存在或不是当前这一次分析")
            code, item = found
            state = item.get("state")
            if state in ("cancelled", "cancelling"):
                return self.queue_snapshot()
            if state == "queued":
                if code not in self._pending or not self._active_job_id:
                    raise QueueConflict("该任务已不在等待队列")
                index = list(self._pending).index(code)
                self._pending.remove(code)
                previous = (item.get("finished_at"), item.get("updated_at"), item.get("error"))
                finished = _now()
                item.update(state="cancelled", error=None, finished_at=finished, updated_at=finished)
                try:
                    saved = refresh_jobs.note_quality_cancel(
                        self._active_job_id, code, list(self._pending))
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
            raise QueueConflict("该次分析已结束")

    def move_item(self, item_id: str, action: str, refresh_jobs) -> dict:
        """只调整仍在等待的项。时间戳不变，顺序先落盘再返回。"""
        if action not in ("front", "up", "down"):
            raise ValueError("不支持的调序动作")
        with self._cond:
            found = self._find_item(item_id)
            if found is None:
                raise QueueConflict("该任务已不存在或不是当前这一次分析")
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
                saved = refresh_jobs.note_quality_order(self._active_job_id, order) if self._active_job_id else None
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

    def _run_one(self, code, hermes_config, submit_run_fn, poll_run_fn, progress, stop_run_fn, get_run_fn) -> None:
        item = self._items[code]
        try:
            kind, score, error, duration, bump = self._execute(
                item, hermes_config, submit_run_fn, poll_run_fn, stop_run_fn, get_run_fn)
        except Exception as exc:  # 未预期异常按该股失败计，避免 _running 不归零
            logger.exception("股票 %s 评级过程异常", code)
            kind, score, error, duration, bump = "failed", None, f"评级过程异常: {exc}"[:300], None, False
        if kind == "completed" and score is not None:
            try:
                self._save_one(score, item["data_date"], duration if duration is not None else 0.0)
            except (OSError, ValueError) as exc:
                logger.exception("评分落盘失败 %s", code)
                kind, error, bump = "failed", f"评分结果保存失败: {exc}", False
        if kind == "cancelled" and bump:
            try:
                self._store_generation(code, int(item.get("cancel_generation") or 0) + 1)
            except OSError:
                logger.exception("取消后的幂等代数未能落盘 %s", code)
        self._finish_item(code, item, kind, error, progress)

    def _execute(self, item, hermes_config, submit_run_fn, poll_run_fn, stop_run_fn, get_run_fn):
        with self._cond:
            cancel_before_submit = bool(item.get("cancel_requested"))
        if cancel_before_submit:
            return "cancelled", None, "", None, False
        started = monotonic()
        expected_version = item["skill_version"]
        prompt = build_prompt(item["payload"], expected_version)
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
            score = parse_quality_output(output, item["code"], item["name"])
            if expected_version and score.skill_version != expected_version:
                raise ValueError(f"skill 版本不符：要求 {expected_version}，实际 {score.skill_version or '未知'}，请检查 Hermes 部署")
        except ValueError as exc:
            text = str(exc)
            prefix = "" if text.startswith("skill 版本不符") or text.startswith("解析失败") else "解析失败: "
            return "failed", None, f"{prefix}{text}"[:300], None, False
        return "completed", score, "", duration, False

    def _finish_item(self, code, item, kind, error, progress) -> None:
        # 先结清进度再归还名额，调度循环才不会在计数写入前把任务收成终态。
        try:
            if kind == "cancelled":
                progress(code, False, outcome="cancelled")
            else:
                if kind != "completed":
                    logger.warning("股票 %s 评级失败: %s", code, error)
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

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

from pydantic import BaseModel, Field, field_validator, model_validator

from src.api.models import DividendStock
from src.services.hermes_client import HermesConfig, HermesError
from src.utils.atomic_file import atomic_write
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

SKILL_NAME = "basic-quality-rating"
QUALITY_FILE = "quality_scores.json"
DIMENSION_WEIGHTS = {"business": 0.25, "moat": 0.25, "industry": 0.20, "management": 0.15, "financial": 0.15}
SCORE_TOLERANCE = 0.01
# 收尾窗口（dispatch loop 已停、job 未落终态）内受理新任务的最长等待秒数
ADMISSION_WAIT_SECONDS = 10.0


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


def build_prompt(payload: dict) -> str:
    """点名 skill + 数据 JSON + 输出约束。"""
    data = json.dumps(payload, ensure_ascii=False)
    return (
        f"请使用 {SKILL_NAME} skill 评估以下股票，严格按 skill 的五维细则与星级映射打分。\n"
        f"最终回复只输出一个 JSON 对象（含 report_md），不要 markdown 代码围栏，不要任何解释文字。\n"
        f"股票数据：{data}"
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

    # ---- 逐股状态 ----

    def get_per_code(self) -> dict:
        with self._cond:
            return {code: {key: item.get(key) for key in
                           ("state", "error", "updated_at", "name",
                            "queued_at", "started_at", "finished_at")}
                    for code, item in self._items.items()}

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

    def _admit(self, ordered: list[str], snapshots: dict[str, dict]) -> None:
        """建队列项并入队（调用方持有 _cond）。重复受理的旧项由调用方处理。"""
        for code in ordered:
            snap = snapshots[code]
            self._items[code] = {
                "code": code, "name": snap["name"], "state": "queued", "error": None,
                "queued_at": _now(), "started_at": None, "finished_at": None, "updated_at": _now(),
                "data_date": snap["data_date"], "payload": snap["payload"],
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
    ) -> Optional[dict]:
        """受理批量评级；返回 job dict（含 reused）或 None（服务关闭中）。

        无任务时开新任务；任务运行中把新代码追加进当前任务（reused=true），已在
        排队/运行的代码幂等跳过且不重置时间戳。未配置、股票不在采集池或收尾等待
        超时时抛 ValueError。
        """
        if not hermes_config.is_configured:
            raise ValueError("Hermes 未配置")
        missing = [code for code in codes if code not in stocks]
        if missing:
            raise ValueError(f"以下股票不在采集池：{','.join(missing)}")
        ordered = list(dict.fromkeys(codes))
        snapshots = {code: {"name": stocks[code].name, "data_date": data_date,
                            "payload": build_stock_payload(stocks[code])}
                     for code in ordered}

        def work(progress: Callable[[str, bool], None]) -> None:
            semaphore = threading.Semaphore(hermes_config.max_concurrent)
            while True:
                with self._cond:
                    while not self._pending and self._running > 0:
                        self._cond.wait()
                    if not self._pending:
                        # 队列清空且无在跑项：此后受理一律开新任务；
                        # 退出判定与追加共用 _cond，追加不会落在此判定之后丢失。
                        self._accepting = False
                        self._active_job_id = None
                        return
                    code = self._pending.popleft()
                    item = self._items[code]
                    started_at = _now()
                    item.update(state="running", started_at=started_at, updated_at=started_at)
                    self._running += 1
                semaphore.acquire()
                threading.Thread(target=self._run_one, daemon=True,
                                 args=(code, hermes_config, submit_run_fn, poll_run_fn,
                                       progress, semaphore)).start()

        with self._cond:
            if self._accepting and self._active_job_id:
                fresh = [code for code in ordered
                         if (self._items.get(code) or {}).get("state") not in ("queued", "running")]
                if not fresh:
                    job = refresh_jobs.get(self._active_job_id)
                    if job:
                        return {**job, "reused": True}
                else:
                    self._admit(fresh, snapshots)
                    updated = refresh_jobs.append_codes(self._active_job_id, fresh)
                    if updated is not None:
                        return {**updated, "reused": True}
                    # job 恰在收尾窗口变终态：撤回刚入队的项，按新任务受理
                    for code in fresh:
                        self._pending.remove(code)
                        self._items.pop(code, None)
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

    def _run_one(self, code, hermes_config, submit_run_fn, poll_run_fn, progress, semaphore) -> None:
        item = self._items[code]
        try:
            try:
                started = monotonic()
                prompt = build_prompt(item["payload"])
                run_id = submit_run_fn(hermes_config, prompt, f"quality-{code}-{item['data_date']}")
                output = poll_run_fn(hermes_config, run_id)
                # Local queueing, parsing and other stocks' runtime are excluded.
                duration = round(monotonic() - started, 3)
                score = parse_quality_output(output, code, item["name"])
            except HermesError as exc:
                outcome = (False, None, str(exc)[:300])
            except ValueError as exc:
                outcome = (False, None, f"解析失败: {exc}")
            except Exception as exc:  # 未预期异常按该股失败计，避免派发循环因 _running 不归零而永久等待
                logger.exception("股票 %s 评级过程异常", code)
                outcome = (False, None, f"评级过程异常: {exc}")
            else:
                outcome = (True, score, "")
        finally:
            semaphore.release()
        success, score, error = outcome
        if success and score is not None:
            try:
                self._save_one(score, item["data_date"], duration)
            except (OSError, ValueError) as exc:
                # ValueError：落盘 JSON 含 NaN 等非法数值（allow_nan=False）
                logger.exception("评分落盘失败 %s", code)
                success, error = False, f"评分结果保存失败: {exc}"
        finished = _now()
        with self._cond:
            item.update(state="completed" if success else "failed",
                        error=None if success else error,
                        finished_at=finished, updated_at=finished)
            self._running -= 1
            self._cond.notify_all()
        if not success:
            logger.warning("股票 %s 评级失败: %s", code, error)
        progress(code, success)

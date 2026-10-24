"""基本面评级编排服务：组装数据 → 提交 Hermes → 解析校验 → 落盘。

评分契约见 skills/basic-quality-rating/SKILL.md「自动化 JSON 输出模式」（五维 1-5 分 + 星级 + report_md）。
批量异步复用 RefreshJobManager（kind='quality'），逐股完成即回调 progress 并合并落盘。
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
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
    dimensions: dict[str, int]
    weighted_score: float
    stars: int
    boundary: Optional[str] = None
    summary: str
    risks: list[str] = Field(default_factory=list)
    watch_points: list[str] = Field(default_factory=list)
    report_md: str

    @field_validator("dimensions")
    @classmethod
    def _dimensions_ok(cls, value: dict[str, int]) -> dict[str, int]:
        if set(value) != set(DIMENSION_WEIGHTS):
            raise ValueError(f"dimensions 键必须为 {sorted(DIMENSION_WEIGHTS)}")
        for key, score in value.items():
            if not isinstance(score, int) or not 1 <= score <= 5:
                raise ValueError(f"维度 {key} 分数须为 1-5 整数，得到 {score}")
        return value

    @model_validator(mode="after")
    def _score_and_stars_consistent(self) -> "QualityScore":
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
    """挑参与评分的字段组装 JSON（缺失传 null，由 skill 按降档规则处理）。"""
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
    """评级编排：入口校验 → RefreshJobManager 异步逐股 submit+poll → 落盘。"""

    def __init__(self, quality_path: Path):
        self.quality_path = quality_path
        self._file_lock = threading.RLock()

    # ---- 落盘读写 ----

    def _read_all(self) -> dict:
        try:
            return json.loads(self.quality_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_one(self, score: QualityScore, data_date: str) -> None:
        scored_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        record = {**score.model_dump(), "scored_at": scored_at, "data_date": data_date}
        with self._file_lock:
            merged = self._read_all()
            merged[score.code] = record
            encoded = json.dumps(merged, ensure_ascii=False, allow_nan=False)
            atomic_write(self.quality_path, lambda p: p.write_text(encoded, encoding="utf-8"))

    def get_all(self) -> dict:
        with self._file_lock:
            return self._read_all()

    # ---- 任务编排 ----

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
        """提交批量评级任务；返回 job dict（含 reused），未配置/股票缺失由调用方前置校验。"""
        if not hermes_config.is_configured:
            raise ValueError("Hermes 未配置")
        missing = [code for code in codes if code not in stocks]
        if missing:
            raise ValueError(f"以下股票不在采集池：{','.join(missing)}")

        def work(progress: Callable[[str, bool], None]) -> None:
            semaphore = threading.Semaphore(hermes_config.max_concurrent)
            results: dict[str, tuple[bool, Optional[QualityScore], str]] = {}

            def run_one(code: str) -> None:
                payload = build_stock_payload(stocks[code])
                prompt = build_prompt(payload)
                idempotency_key = f"quality-{code}-{data_date}"
                try:
                    run_id = submit_run_fn(hermes_config, prompt, idempotency_key)
                    output = poll_run_fn(hermes_config, run_id)
                    score = parse_quality_output(output, code, stocks[code].name)
                except HermesError as exc:
                    results[code] = (False, None, str(exc)[:300])
                except ValueError as exc:
                    results[code] = (False, None, f"解析失败: {exc}")
                else:
                    results[code] = (True, score, "")
                finally:
                    semaphore.release()

            threads = []
            for code in codes:
                semaphore.acquire()
                thread = threading.Thread(target=run_one, args=(code,), daemon=True)
                thread.start()
                threads.append(thread)
            for thread in threads:
                thread.join()

            for code in codes:
                success, score, error = results.get(code, (False, None, "内部错误：无结果"))
                if success and score is not None:
                    try:
                        self._save_one(score, data_date)
                    except OSError as exc:
                        logger.exception("评分落盘失败 %s", code)
                        progress(code, False)
                        continue
                elif not success:
                    logger.warning("股票 %s 评级失败: %s", code, error)
                progress(code, success)

        return refresh_jobs.submit("quality", codes, work, params={"data_date": data_date})

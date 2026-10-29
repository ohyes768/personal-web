"""指数趋势服务：刷新、模型计算、图表与当前状态。

刷新流程（带锁互斥，由 API/调度共用）：
  1. 拉月K+日线（腾讯），校验（有序唯一、OHLC、完整月判定、连续性）
  2. 完整月序列落库；未完成月仅展示，不参加拟合
  3. 按 (指数, 种类, 训练起止, 算法版本, 数据哈希) 幂等生成模型版本：
     同月内价格变化不改变完整月序列 → 哈希与系数不变（AC4）
  4. data_meta 记录供应商、抓取时间、截止月与哈希
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from src.core import months as mutils
from src.core.models import (
    CURRENT_MODEL_KINDS,
    INCEPTION_MONTH,
    KIND_FIXED,
    KIND_SINCE_INCEPTION,
    KIND_TRAILING,
    ModelRecord,
    build_model_id,
    classify_region,
    data_hash,
    position_pct,
)
from src.core.regression import ALGORITHM_VERSION, DEFAULT_MULTIPLIER, channel_at, fit_channel
from src.core.windows import OBSERVATION_MONTHS, WINDOW_MONTHS, generate_fixed_windows
from src.data import provider as pv
from src.data.validate import (
    MonthlySeries,
    build_complete_monthly_series,
    latest_completed_daily,
    to_month_key,
)
from src.services.store import Store, now_iso

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
INDEX_CODE = "000300"
SYMBOL = "sh000300"
INDEX_NAME = "沪深300"
TRAILING_MONTHS = 120
FUTURE_EXTENSION_MONTHS = 12  # 当前页趋势延伸长度（PRD 建议值）


@dataclass(frozen=True)
class RefreshResult:
    success: bool
    message: str
    data_cutoff_month: str | None = None
    new_models: list[str] | None = None
    monthly_count: int | None = None


def model_to_dict(model: ModelRecord) -> dict[str, Any]:
    return {
        "model_id": model.model_id,
        "index_code": model.index_code,
        "kind": model.kind,
        "fit_start": model.fit_start,
        "fit_end": model.fit_end,
        "months": model.months,
        "algorithm_version": model.algorithm_version,
        "data_cutoff_month": model.data_cutoff_month,
        "multiplier": model.multiplier,
        "calculated_at": model.calculated_at,
        "coefficients": {
            "slope": model.coefficients.slope,
            "intercept": model.coefficients.intercept,
            "deviation": model.coefficients.deviation,
        },
    }


class TrendService:
    def __init__(
        self,
        store: Store,
        refresh_lock: asyncio.Lock | None = None,
        now_fn: Any | None = None,
    ):
        self.store = store
        self.refresh_lock = refresh_lock or asyncio.Lock()
        self._now_fn = now_fn or (lambda: datetime.now(SHANGHAI_TZ))

    # ---- 刷新 ----
    def refresh_sync(self, client: httpx.Client | None = None) -> RefreshResult:
        """拉取行情并重算模型（同步，供线程池与测试调用）。"""
        own_client = client is None
        client = client or pv.new_client()
        try:
            monthly_bars = pv.fetch_kline(SYMBOL, "month", 1000, client)
            daily_bars = pv.fetch_kline(SYMBOL, "day", 320, client)
        finally:
            if own_client:
                client.close()

        series = build_complete_monthly_series(
            monthly_bars, today=self._today(), inception_month=INCEPTION_MONTH
        )
        cutoff = series.months[-1]
        self.store.upsert_monthly_bars({to_month_key(b.date): b for b in monthly_bars})
        self.store.upsert_daily_quotes(daily_bars)

        new_models: list[str] = []
        for record in self._compute_models(series, cutoff):
            if self.store.upsert_model(record):
                new_models.append(record.model_id)
        self.store.set_data_meta(pv.__name__, cutoff, data_hash(series.closes))
        return RefreshResult(
            success=True,
            message=f"已刷新至 {cutoff}，共 {len(series.months)} 个完整月",
            data_cutoff_month=cutoff,
            new_models=new_models,
            monthly_count=len(series.months),
        )

    async def refresh(self) -> RefreshResult:
        """互斥刷新：手动 API 与调度任务共用同一把锁。"""
        async with self.refresh_lock:
            return await asyncio.to_thread(self.refresh_sync)

    def _compute_models(self, series: MonthlySeries, cutoff: str) -> list[ModelRecord]:
        closes, month_list = series.closes, series.months
        records: list[ModelRecord] = []

        def make(kind: str, seg: list[float], seg_start: str, seg_end: str, cutoff_month: str) -> ModelRecord:
            coeff = fit_channel(seg, DEFAULT_MULTIPLIER)
            h = data_hash(seg)
            return ModelRecord(
                model_id=build_model_id(INDEX_CODE, kind, seg_start, seg_end, h, ALGORITHM_VERSION),
                index_code=INDEX_CODE,
                kind=kind,
                fit_start=seg_start,
                fit_end=seg_end,
                months=len(seg),
                algorithm_version=ALGORITHM_VERSION,
                data_cutoff_month=cutoff_month,
                data_hash=h,
                multiplier=DEFAULT_MULTIPLIER,
                coefficients=coeff,
                calculated_at=now_iso(),
            )

        # 固定窗口：训练数据定死，cutoff 记 fit_end → model_id 终身稳定，不随全局数据更新
        for w in generate_fixed_windows(month_list):
            start_idx = mutils.month_sequence_index(w.start_month, month_list[0])
            records.append(
                make(KIND_FIXED, closes[start_idx : start_idx + WINDOW_MONTHS], w.start_month, w.end_month, w.end_month)
            )
        # 近10年 = 最近 120 个完整自然月（不是最后一个固定步进窗口）
        if len(closes) >= TRAILING_MONTHS:
            n = len(closes)
            records.append(
                make(KIND_TRAILING, closes[n - TRAILING_MONTHS :], month_list[n - TRAILING_MONTHS], month_list[n - 1], cutoff)
            )
        # 成立以来 = 全样本；全历史回溯图与当前页"成立以来"共用该模型
        records.append(make(KIND_SINCE_INCEPTION, closes, month_list[0], month_list[-1], cutoff))
        return records

    # ---- 图表 ----
    def build_chart(self, model: ModelRecord, extend_until: str | None) -> dict[str, Any]:
        """按模型构建图表数据。

        extend_until: 延伸区截止月。None = 不延伸（全历史回溯）；
        未来月份 = 趋势投影（无价格）；过去月份 = 拟合后实际观察区。
        轨道延伸按自然月整数序号投影；拟合与展示时间坐标一致。
        """
        bars = self.store.load_monthly_bars()
        all_months = sorted(bars)
        today_str = self._today().isoformat()
        current_m = mutils.current_month(self._today())

        fit_months = [m for m in all_months if model.fit_start <= m <= model.fit_end]
        if len(fit_months) != model.months:
            raise ValueError(
                f"模型 {model.model_id} 与库内数据不匹配: 需要 {model.months} 个月, 实际 {len(fit_months)}"
            )

        # 延伸月序列：fit_end+1 起，截止 extend_until（可为未来月）
        ext_months: list[str] = []
        if extend_until is not None and mutils.months_between(model.fit_end, extend_until) > 0:
            total = mutils.months_between(model.fit_end, extend_until)
            ext_months = [mutils.shift_month(model.fit_end, i + 1) for i in range(total)]

        # 价格 bars：展示范围内实际存在的月（含当前未完成月）
        display_end = extend_until if extend_until is not None else model.fit_end
        if extend_until is not None and display_end < model.fit_end:
            display_end = model.fit_end
        price_months = [m for m in all_months if model.fit_start <= m <= display_end]
        bars_out = []
        for month in price_months:
            b = bars[month]
            bars_out.append(
                {
                    "month": month,
                    "date": b.date,
                    "open": b.open,
                    "close": b.close,
                    "high": b.high,
                    "low": b.low,
                    "partial": month == current_m,  # 未完成自然月标记
                }
            )

        def series_for(month_seq: list[str]) -> dict[str, Any]:
            mids, uppers, lowers = [], [], []
            for month in month_seq:
                x = mutils.month_sequence_index(month, model.fit_start)
                mid, upper, lower = channel_at(model.coefficients, x, model.multiplier)
                mids.append(round(mid, 4))
                uppers.append(round(upper, 4))
                lowers.append(round(lower, 4))
            return {"months": month_seq, "mid": mids, "upper": uppers, "lower": lowers}

        # 延伸序列以拟合末端点开头，保证虚线与实线连续
        ext_series = series_for([model.fit_end] + ext_months) if ext_months else None
        future_note = bool(ext_months and ext_months[-1] > current_m)

        return {
            "model": model_to_dict(model),
            "bars": bars_out,
            "fit_series": series_for(fit_months),
            "extension_series": ext_series,
            "fit_boundary_month": model.fit_end,
            "extend_note": (
                "延伸区间为按模型斜率的趋势投影，仅供参考，非目标价"
                if future_note
                else ("拟合结束后的价格观察区，模型保持不变" if ext_months else None)
            ),
        }

    # ---- 当前状态 ----
    def current_status(self, model_kind: str) -> dict[str, Any]:
        """指定当前模型的最新收盘、区域与位置。

        同一份最新价格在两个模型下可处于不同区域；切换模型时全部数值
        都来自所选模型，无跨模型缓存。
        """
        model = self.store.latest_model(INDEX_CODE, model_kind)
        if model is None:
            return {"available": False, "reason": "model_not_ready", "model_kind": model_kind}
        dailies = self.store.load_daily_quotes(limit=50)
        last = latest_completed_daily(dailies, self._now())
        if last is None:
            return {"available": False, "reason": "no_daily_data", "model_kind": model_kind}

        proj_month = to_month_key(last.date)
        x = mutils.month_sequence_index(proj_month, model.fit_start)
        mid, upper, lower = channel_at(model.coefficients, x, model.multiplier)
        try:
            pct = position_pct(last.close, upper, lower)
            region = classify_region(pct)
        except ValueError as e:
            return {
                "available": False,
                "reason": "invalid_channel",
                "model_kind": model_kind,
                "model": model_to_dict(model),
                "error": str(e),
            }
        return {
            "available": True,
            "model_kind": model_kind,
            "model": model_to_dict(model),
            "price_as_of": last.date,
            "close": last.close,
            "projection_month": proj_month,
            "upper": round(upper, 4),
            "mid": round(mid, 4),
            "lower": round(lower, 4),
            "position_pct": round(pct, 2),
            "region": region,
            "data_status": self.data_status(),
        }

    # ---- 元数据 ----
    def data_status(self) -> dict[str, Any]:
        """数据新鲜度：缺失月份、过期、供应商异常均为可见状态。"""
        meta = self.store.get_data_meta()
        today = self._today()
        current_m = mutils.current_month(today)
        expected_cutoff = mutils.shift_month(current_m, -1)
        cutoff = meta.get("monthly_cutoff_month")
        dailies = self.store.load_daily_quotes(limit=1)
        daily_last = dailies[0].date if dailies else None
        if not cutoff:
            state = "empty"
        elif cutoff < mutils.shift_month(current_m, -2):
            state = "stale"  # 落后超过 2 个自然月
        else:
            state = "ok"
        return {
            "state": state,
            "data_cutoff_month": cutoff,
            "expected_cutoff_month": expected_cutoff,
            "daily_last_date": daily_last,
            "captured_at": meta.get("captured_at"),
            "provider": "Tencent Finance" if meta.get("provider") else None,
        }

    def history_overview(self) -> dict[str, Any]:
        """历史回溯 Tab 选择器元数据：固定窗口 + 全历史。"""
        windows = []
        for model in self.store.list_models(INDEX_CODE, KIND_FIXED):
            windows.append(
                {
                    "stable_id": f"fixed-{model.fit_start}",
                    "window": len(windows) + 1,
                    "fit_start": model.fit_start,
                    "fit_end": model.fit_end,
                    "observation_end_month": self._observation_end(model.fit_start, model.fit_end),
                    "model_id": model.model_id,
                }
            )
        since = self.store.latest_model(INDEX_CODE, KIND_SINCE_INCEPTION)
        return {
            "index_code": INDEX_CODE,
            "name": INDEX_NAME,
            "windows": windows,
            "all_history": (
                {
                    "stable_id": "all",
                    "fit_start": since.fit_start,
                    "fit_end": since.fit_end,
                    "sample_fitted": True,
                    "model_id": since.model_id,
                    "note": "全样本拟合：以全部历史数据拟合，非2005年时点已知通道，不构成样本外验证",
                }
                if since
                else None
            ),
            "data_status": self.data_status(),
        }

    def indices_overview(self) -> dict[str, Any]:
        current_models = {}
        for kind in (KIND_TRAILING, KIND_SINCE_INCEPTION):
            model = self.store.latest_model(INDEX_CODE, kind)
            if model:
                current_models[kind] = model_to_dict(model)
        return {
            "indices": [
                {
                    "index_code": INDEX_CODE,
                    "name": INDEX_NAME,
                    "symbol": SYMBOL,
                    "kind": "price_index",
                    "inception_month": INCEPTION_MONTH,
                    "available_model_kinds": list(CURRENT_MODEL_KINDS) + [KIND_FIXED],
                    "current_models": current_models,
                }
            ],
            "data_status": self.data_status(),
        }

    def _last_complete_month(self) -> str:
        bars = self.store.load_monthly_bars()
        complete = [m for m in sorted(bars) if mutils.is_complete_month(m, self._today())]
        return complete[-1] if complete else ""

    def _observation_end(self, fit_start: str, fit_end: str) -> str | None:
        """窗口后续观察区实际截止月（样本不足时仅展示实际可用部分）。"""
        last = self._last_complete_month()
        if not last or mutils.months_between(fit_end, last) <= 0:
            return None
        capped = mutils.shift_month(fit_end, OBSERVATION_MONTHS)
        return min(capped, last)

    def _now(self) -> datetime:
        return self._now_fn()

    def _today(self) -> date:
        return self._now_fn().date()

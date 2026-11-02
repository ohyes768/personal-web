"""指数趋势服务：刷新、模型计算、图表与当前状态。

月线刷新流程（带锁互斥，由 API/调度共用）：
  1. 拉月K+日线（腾讯），校验（有序唯一、OHLC、完整月判定、连续性）
  2. 完整月序列落库；未完成月仅展示，不参加拟合
  3. 按 (指数, 种类, 训练起止, 算法版本, 数据哈希) 幂等生成模型版本：
     同月内价格变化不改变完整月序列 → 哈希与系数不变（AC4）
  4. data_meta 记录供应商、抓取时间、截止月与哈希

周线刷新流程（WeeklyTrendService，design.md 第 2/4 节）严格分三段：
  1. 取数校验：拉周K+日线，按交易日历判定完整周、区分缺失/休市/日历越界
  2. 纯计算：内存中算完所有模型（周坐标、显式 x、版本哈希）
  3. 事务发布：单个 SQLite 事务写周K/日线/模型/元数据；失败整体回滚，
     旧成功快照仍可读
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from src.core import months as mutils
from src.core.models import (
    CURRENT_MODEL_KINDS,
    CURRENT_WEEKLY_MODEL_KINDS,
    INCEPTION_MONTH,
    KIND_FIXED,
    KIND_FIXED_WEEKLY,
    KIND_SINCE_INCEPTION,
    KIND_SINCE_INCEPTION_WEEKLY,
    KIND_TRAILING,
    KIND_TRAILING_WEEKLY,
    LEGACY_KIND_TO_WEEKLY,
    ModelRecord,
    WeeklyModelRecord,
    build_model_id,
    classify_region,
    data_hash,
    position_pct,
    weekly_data_hash,
)
from src.core.regression import ALGORITHM_VERSION, DEFAULT_MULTIPLIER, channel_at, fit_channel
from src.core.windows import OBSERVATION_MONTHS, WINDOW_MONTHS, generate_fixed_windows
from src.core.weekly import WeeklyModelBuilder, project_week
from src.core.weeks import FIXED_WINDOW_OBSERVATION_YEARS, shift_years
from src.data import provider as pv
from src.data.trading_calendar import CalendarUnavailableError, TradingCalendar, XshgTradingCalendar
from src.data.validate import (
    MonthlySeries,
    WeeklySeries,
    build_complete_monthly_series,
    build_weekly_series,
    check_weekly_daily_consistency,
    expected_last_complete_week,
    expected_last_session,
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

# 周线：当前页趋势延伸长度（52 个自然周 ≈ 1 年）
FUTURE_EXTENSION_WEEKS = 52
# 周K 拉取条数（覆盖 2005-04 至今需要约 1100 条，取 1600 留余量）
WEEKLY_REQUEST_COUNT = 1600
# 日线拉取条数（最近已完成交易日定位 + 周K收盘交叉校验）
WEEKLY_DAILY_REQUEST_COUNT = 320
# 周线数据必须覆盖到的起点（沪深300 发布周）
WEEKLY_INCEPTION_WEEK = "2005-04-04"


@dataclass(frozen=True)
class RefreshResult:
    success: bool
    message: str
    data_cutoff_month: str | None = None
    new_models: list[str] | None = None
    monthly_count: int | None = None


def weekly_model_to_dict(model: WeeklyModelRecord) -> dict[str, Any]:
    """周线模型的 API 形状。不把周数写进 months。"""
    return {
        "model_id": model.model_id,
        "index_code": model.index_code,
        "kind": model.kind,
        "timeframe": model.timeframe,
        "fit_start": model.fit_start,
        "fit_end": model.fit_end,
        "fit_last_trade_date": model.fit_last_trade_date,
        "sample_count": model.sample_count,
        "calendar_window_start": model.calendar_window_start,
        "calendar_window_end": model.calendar_window_end,
        "data_cutoff_week": model.data_cutoff_week,
        "algorithm_version": model.algorithm_version,
        "multiplier": model.multiplier,
        "calculated_at": model.calculated_at,
        "coefficients": {
            "slope": model.coefficients.slope,
            "intercept": model.coefficients.intercept,
            "deviation": model.coefficients.deviation,
        },
    }


def resolve_weekly_kind(kind: str) -> str:
    """旧月线 kind 别名解析为周线 kind。无法解析时原样返回，由调用方拒绝。"""
    return LEGACY_KIND_TO_WEEKLY.get(kind, kind)


def iter_week_starts(start: str, end: str) -> list[str]:
    """含首尾的自然周周一序列。start 晚于 end 时为空。"""
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    weeks: list[str] = []
    while cur <= last:
        weeks.append(cur.isoformat())
        cur += timedelta(days=7)
    return weeks


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


# ---- 周线服务 ----


@dataclass(frozen=True)
class WeeklyRefreshResult:
    """周线刷新结果。"""

    success: bool
    message: str
    data_cutoff_week: str | None = None
    data_cutoff_trade_date: str | None = None
    weekly_count: int | None = None
    new_models: list[str] | None = None
    snapshot_id: str | None = None


def compute_snapshot_id(
    data_cutoff_week: str,
    weekly_hash: str,
    model_ids: list[str],
) -> str:
    """快照标识：同一份数据 + 同一批模型 → 同一标识。

    读端用它判断两次请求是否来自同一快照，避免图表与摘要混画。
    """
    payload = json.dumps(
        [data_cutoff_week, weekly_hash, sorted(model_ids)], separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class WeeklyTrendService:
    """周线趋势服务：取数校验 → 纯计算 → 事务发布，三段严格分离。

    与月线 TrendService 并存但完全隔离：独立表、独立模型种类、
    独立算法版本。月线路径不受影响。
    """

    def __init__(
        self,
        store: Store,
        refresh_lock: asyncio.Lock | None = None,
        now_fn: Any | None = None,
        calendar: TradingCalendar | None = None,
    ):
        self.store = store
        self.refresh_lock = refresh_lock or asyncio.Lock()
        self._now_fn = now_fn or (lambda: datetime.now(SHANGHAI_TZ))
        self._calendar = calendar

    # ---- 1. 取数与校验 ----
    def fetch_and_validate(
        self, client: httpx.Client | None = None
    ) -> tuple[WeeklySeries, list[Any]]:
        """拉取周K与日线并按交易日历校验。

        校验失败抛异常（缺失行情 / 日历越界 / 最后交易日不一致），
        由调用方转为可见状态，不静默降级。
        """
        own_client = client is None
        client = client or pv.new_client()
        try:
            weekly_bars = pv.fetch_kline(SYMBOL, "week", WEEKLY_REQUEST_COUNT, client)
            daily_bars = pv.fetch_kline(SYMBOL, "day", WEEKLY_DAILY_REQUEST_COUNT, client)
        finally:
            if own_client:
                client.close()

        if not weekly_bars:
            raise ValueError("周K数据为空")
        earliest = min(b.date for b in weekly_bars)
        if earliest > "2005-04-30":
            raise ValueError(f"周K未覆盖 2005-04 起点（最早 {earliest}）")

        calendar = self.trading_calendar()
        series = build_weekly_series(weekly_bars, calendar, self._now())

        # 日线必须覆盖当前时刻最近应已收盘的会话日
        expected = expected_last_session(calendar, self._now())
        daily_closes = {b.date: b.close for b in daily_bars}
        if expected is not None and expected.isoformat() not in daily_closes:
            raise ValueError(f"日线未覆盖最近应已收盘的会话日: {expected}")

        # 周K收盘与当周最后交易日日线交叉校验（0.01 显示精度容差）
        for sample in series.samples[-60:]:
            bar = series.week_of(sample.week_start)
            if bar is None:
                continue
            if not check_weekly_daily_consistency(bar, daily_closes):
                raise ValueError(
                    f"周K收盘与日线不一致: {sample.week_start} 周K {bar.close} "
                    f"日线 {daily_closes.get(sample.trade_date)}"
                )
        return series, daily_bars

    # ---- 2. 纯计算 ----
    def compute_models(self, series: WeeklySeries) -> list[Any]:
        """在内存中算完所有周线模型（不落库）。"""
        builder = WeeklyModelBuilder(
            series, INDEX_CODE, self._today(), DEFAULT_MULTIPLIER, now_iso()
        )
        return builder.build_all()

    # ---- 3. 事务发布 ----
    def publish(
        self,
        series: WeeklySeries,
        daily_bars: list[Any],
        models: list[Any],
    ) -> WeeklyRefreshResult:
        """单个事务发布周K、日线、模型与元数据；失败整体回滚。"""
        cutoff_week = series.samples[-1].week_start
        cutoff_trade_date = series.samples[-1].trade_date
        # 快照哈希必须带周坐标。只散列收盘会把“同一批价格、不同周位置”
        # （例如整周休市挪位）当成同一份数据。
        weekly_hash = weekly_data_hash(series.complete_weeks, series.closes)
        snapshot_id = compute_snapshot_id(
            cutoff_week, weekly_hash, [m.model_id for m in models]
        )
        bars = {
            sample.week_start: pv.KlineBar(
                date=sample.trade_date,
                open=sample.open,
                close=sample.close,
                high=sample.high,
                low=sample.low,
            )
            for sample in series.samples
        }
        result = self.store.publish_weekly_snapshot(
            bars=bars,
            models=models,
            provider="Tencent Finance",
            data_cutoff_week=cutoff_week,
            data_cutoff_trade_date=cutoff_trade_date,
            weekly_hash=weekly_hash,
            snapshot_id=snapshot_id,
            partial_bars={
                week: pv.KlineBar(
                    date=bar.date,
                    open=bar.open,
                    close=bar.close,
                    high=bar.high,
                    low=bar.low,
                )
                for week, bar in series.partial_bars.items()
            },
            daily_bars=daily_bars,
        )
        self.store.clear_weekly_failure()
        return WeeklyRefreshResult(
            success=True,
            message=f"已刷新至 {cutoff_week}，共 {len(series.samples)} 个完整周",
            data_cutoff_week=cutoff_week,
            data_cutoff_trade_date=cutoff_trade_date,
            weekly_count=len(series.samples),
            new_models=result["new_model_ids"],
            snapshot_id=snapshot_id,
        )

    # ---- 编排 ----
    def refresh_sync(self, client: httpx.Client | None = None) -> WeeklyRefreshResult:
        """取数校验 → 纯计算 → 事务发布（同步，供线程池与测试调用）。

        失败时记录失败状态（旧成功快照仍可读），异常继续上抛由调用方决定
        如何呈现——不静默降级成"正常但数据旧"。
        """
        try:
            series, daily_bars = self.fetch_and_validate(client)
            models = self.compute_models(series)
            return self.publish(series, daily_bars, models)
        except Exception as e:  # noqa: BLE001 — 失败状态要落库，异常继续上抛
            self.store.record_weekly_failure(str(e))
            raise

    async def refresh(self) -> WeeklyRefreshResult:
        """互斥刷新：手动 API 与调度任务共用同一把锁。"""
        async with self.refresh_lock:
            return await asyncio.to_thread(self.refresh_sync)

    def trading_calendar(self) -> TradingCalendar:
        """进程内缓存日历。未注入时用 SSE；测试可传入显式会话集。"""
        if self._calendar is None:
            self._calendar = XshgTradingCalendar()
        return self._calendar

    def resolve_current_kind(self, kind: str) -> str:
        """当前页模型种类。旧月线别名落到对应周线种类，其他值拒绝。"""
        mapped = resolve_weekly_kind(kind)
        if mapped not in CURRENT_WEEKLY_MODEL_KINDS:
            raise ValueError(kind)
        return mapped

    def weekly_model_by_id(self, model_id: str) -> WeeklyModelRecord | None:
        return next(
            (item for item in self.store.list_weekly_models(INDEX_CODE) if item.model_id == model_id),
            None,
        )

    def monthly_model_by_id(self, model_id: str) -> ModelRecord | None:
        return next(
            (item for item in self.store.list_models(INDEX_CODE) if item.model_id == model_id),
            None,
        )

    def build_chart(self, model: WeeklyModelRecord, scope: str) -> dict[str, Any]:
        """按周线模型构建图表。

        scope=current：自拟合末端延伸 52 个自然周，注明趋势参考而非目标价。
        scope=history：固定窗口延伸到观察区实际截止；成立以来不延伸。
        拟合与延伸使用同一套自然周周一坐标，整周休市留时间槽、不填造 K 线。
        """
        if scope == "current":
            extend_until = (
                date.fromisoformat(model.fit_end) + timedelta(weeks=FUTURE_EXTENSION_WEEKS)
            ).isoformat()
            future = True
        elif model.kind == KIND_SINCE_INCEPTION_WEEKLY:
            extend_until = None
            future = False
        elif model.kind == KIND_FIXED_WEEKLY:
            extend_until = self._observation_end_week(model)
            future = False
        else:
            extend_until = None
            future = False

        fit_weeks = iter_week_starts(model.fit_start, model.fit_end)
        ext_weeks = (
            iter_week_starts(model.fit_end, extend_until)
            if extend_until and extend_until > model.fit_end
            else []
        )
        display_end = ext_weeks[-1] if ext_weeks else model.fit_end

        complete = self.store.load_weekly_bars(include_partial=False)
        partial = self.store.load_partial_weekly_bars()
        merged = {**complete, **partial}
        bars_out = []
        for week in sorted(merged):
            if not (model.fit_start <= week <= display_end):
                continue
            bar = merged[week]
            bars_out.append(
                {
                    "week_start": week,
                    "date": bar.date,
                    "open": bar.open,
                    "close": bar.close,
                    "high": bar.high,
                    "low": bar.low,
                    "partial": week in partial,
                }
            )

        def series_for(weeks: list[str]) -> dict[str, Any]:
            mids, uppers, lowers = [], [], []
            origin = date.fromisoformat(model.fit_start)
            for week in weeks:
                x = (date.fromisoformat(week) - origin).days / 7
                mid, upper, lower = channel_at(model.coefficients, x, model.multiplier)
                mids.append(round(mid, 4))
                uppers.append(round(upper, 4))
                lowers.append(round(lower, 4))
            return {"weeks": weeks, "mid": mids, "upper": uppers, "lower": lowers}

        if future and ext_weeks:
            extend_note = "延伸区间为按模型斜率的趋势投影，仅供参考，非目标价"
        elif ext_weeks:
            extend_note = "拟合结束后的价格观察区，模型保持不变"
        else:
            extend_note = None

        meta = self.store.get_weekly_data_meta()
        return {
            "model": weekly_model_to_dict(model),
            "bars": bars_out,
            "fit_series": series_for(fit_weeks),
            "extension_series": series_for(ext_weeks) if ext_weeks else None,
            "fit_boundary_week": model.fit_end,
            "extend_note": extend_note,
            "snapshot_id": meta.get("snapshot_id") or None,
        }

    def current_status(self, model_kind: str) -> dict[str, Any]:
        """指定当前周线模型的最新收盘、区域与位置。

        投影周是最近已完成交易日所在自然周；进行中周的点位不触发重拟合。
        切换模型时轨道、位置、样本周全部来自该模型。
        """
        model = self.store.latest_weekly_model(INDEX_CODE, model_kind)
        status = self.data_status()
        if model is None:
            return {
                "available": False,
                "reason": "model_not_ready",
                "model_kind": model_kind,
                "data_status": status,
                "snapshot_id": status.get("snapshot_id"),
            }
        dailies = self.store.load_daily_quotes(limit=400)
        last = latest_completed_daily(dailies, self._now())
        if last is None:
            return {
                "available": False,
                "reason": "no_daily_data",
                "model_kind": model_kind,
                "model": weekly_model_to_dict(model),
                "data_status": status,
                "snapshot_id": status.get("snapshot_id"),
            }
        projection = date.fromisoformat(last.date)
        week = (projection - timedelta(days=projection.weekday())).isoformat()
        try:
            mid, upper, lower, pct = project_week(
                model.coefficients, model.multiplier, model.fit_start, week, last.close
            )
            region = classify_region(pct)
        except ValueError as exc:
            return {
                "available": False,
                "reason": "invalid_channel",
                "model_kind": model_kind,
                "model": weekly_model_to_dict(model),
                "error": str(exc),
                "data_status": status,
                "snapshot_id": status.get("snapshot_id"),
            }
        return {
            "available": True,
            "model_kind": model_kind,
            "model": weekly_model_to_dict(model),
            "price_as_of": last.date,
            "close": last.close,
            "projection_week": week,
            "upper": round(upper, 4),
            "mid": round(mid, 4),
            "lower": round(lower, 4),
            "position_pct": round(pct, 2),
            "region": region,
            "data_status": status,
            "snapshot_id": status.get("snapshot_id"),
        }

    def data_status(self) -> dict[str, Any]:
        """周线新鲜度。过期仍可读；失败、日历越界与空库分开标记。"""
        meta = self.store.get_weekly_data_meta()
        cutoff = meta.get("data_cutoff_week") or None
        snapshot_id = meta.get("snapshot_id") or None
        last_error = meta.get("last_error") or None
        dailies = self.store.load_daily_quotes(limit=1)
        daily_last = dailies[0].date if dailies else None

        expected_week: str | None = None
        expected_close: str | None = None
        calendar_error: str | None = None
        try:
            calendar = self.trading_calendar()
            expected = expected_last_complete_week(calendar, self._now())
            if expected is not None:
                expected_week = expected.isoformat()
                sessions = calendar.sessions(expected, expected + timedelta(days=6))
                if sessions:
                    expected_close = sessions[-1].isoformat()
        except CalendarUnavailableError as exc:
            calendar_error = str(exc)

        if calendar_error:
            state, reason = "error", f"calendar_unavailable: {calendar_error}"
        elif last_error:
            state, reason = "error", last_error
        elif not cutoff:
            state, reason = "empty", None
        elif expected_week and cutoff < expected_week:
            state, reason = "stale", None
        else:
            state, reason = "ok", None
        return {
            "state": state,
            "data_cutoff_week": cutoff,
            "expected_cutoff_week": expected_week,
            "expected_close_date": expected_close,
            "daily_last_date": daily_last,
            "captured_at": meta.get("captured_at") or None,
            "reason": reason,
            "snapshot_id": snapshot_id,
            "provider": meta.get("provider") or None,
        }

    def history_overview(self) -> dict[str, Any]:
        """历史回溯：固定 10 年窗口 + 全历史（与成立以来共用模型）。"""
        windows = []
        for index, model in enumerate(
            self.store.list_weekly_models(INDEX_CODE, KIND_FIXED_WEEKLY), start=1
        ):
            windows.append(
                {
                    "stable_id": model.stable_id,
                    "window": index,
                    "calendar_window_start": model.calendar_window_start,
                    "calendar_window_end": model.calendar_window_end,
                    "fit_start": model.fit_start,
                    "fit_end": model.fit_end,
                    "observation_end_week": self._observation_end_week(model),
                    "sample_count": model.sample_count,
                    "model_id": model.model_id,
                }
            )
        since = self.store.latest_weekly_model(INDEX_CODE, KIND_SINCE_INCEPTION_WEEKLY)
        return {
            "index_code": INDEX_CODE,
            "name": INDEX_NAME,
            "windows": windows,
            "all_history": (
                {
                    "stable_id": "all",
                    "calendar_window_start": since.calendar_window_start,
                    "calendar_window_end": since.calendar_window_end,
                    "fit_start": since.fit_start,
                    "fit_end": since.fit_end,
                    "observation_end_week": None,
                    "sample_count": since.sample_count,
                    "model_id": since.model_id,
                    "note": "全样本拟合：以全部历史周线拟合，非2005年时点已知通道，不构成样本外验证",
                }
                if since
                else None
            ),
            "data_status": self.data_status(),
        }

    def indices_overview(self) -> dict[str, Any]:
        current_models = {}
        for kind in (KIND_TRAILING_WEEKLY, KIND_SINCE_INCEPTION_WEEKLY):
            model = self.store.latest_weekly_model(INDEX_CODE, kind)
            if model:
                current_models[kind] = weekly_model_to_dict(model)
        return {
            "indices": [
                {
                    "index_code": INDEX_CODE,
                    "name": INDEX_NAME,
                    "symbol": SYMBOL,
                    "kind": "price_index",
                    "inception_week": WEEKLY_INCEPTION_WEEK,
                    "available_model_kinds": [KIND_TRAILING_WEEKLY, KIND_SINCE_INCEPTION_WEEKLY, KIND_FIXED_WEEKLY],
                    "current_models": current_models,
                }
            ],
            "data_status": self.data_status(),
        }

    def _observation_end_week(self, model: WeeklyModelRecord) -> str | None:
        """固定窗口观察期实际截止周（周一）。样本外价格不参与拟合。"""
        if model.kind != KIND_FIXED_WEEKLY:
            return None
        start = date.fromisoformat(model.calendar_window_end)
        end = shift_years(start, FIXED_WINDOW_OBSERVATION_YEARS)
        bars = self.store.load_weekly_bars(include_partial=False)
        candidates = [week for week in bars if start <= date.fromisoformat(week) < end]
        return max(candidates) if candidates else None

    def _now(self) -> datetime:
        return self._now_fn()

    def _today(self) -> date:
        return self._now_fn().date()

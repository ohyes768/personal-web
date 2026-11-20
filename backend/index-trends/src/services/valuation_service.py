"""估值服务：理杏仁指数估值（PB 主、PE-TTM 辅）的近 10 年分位。

职责边界：
- 本服务决定**目标日**（页面与每日采集：最近一个已收盘交易日）、采集状态与缓存；
  不把估值混进趋势模型算法。
- 分位直接采用供应商统计值（0–1 的比例 → 0–100%），不在本地重新计算。
- 一个指数一次请求取回 PE-TTM 与 PB 两条指标；两条指标各自记账、各自判状态，
  一条失败不把另一条抹成失败。
- 没有 Token 时正常启动并返回 disabled 状态；估值问题不阻断行情、图表与查询。

对外统一对象（按指标）：
    state: ok / stale / empty / error / disabled
    reason: 固定错误码（不含供应商正文与 Token）
    metric / source / window: 口径标识
    target_date: 期望的数据日期
    as_of: 实际数据日期
    value / percentile_pct: 数值（缺失用 null，不用 0）
    captured_at: 采集时间
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta
from typing import Any, Callable, Sequence
from zoneinfo import ZoneInfo

from src.core.indexes import BY_CODE, DEFAULT_INDEX_CODE, index_codes
from src.data import lixinger as lx
from src.data.trading_calendar import CalendarUnavailableError, TradingCalendar
from src.data.validate import expected_last_session
from src.services.store import Store

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

STATE_OK = "ok"
STATE_STALE = "stale"
STATE_EMPTY = "empty"
STATE_ERROR = "error"
STATE_DISABLED = "disabled"

# 失败后的最小重试间隔（同一目标日）
RETRY_COOLDOWN = timedelta(minutes=15)

# 首次采集回填的历史长度：分位走势图要能画出整段 10 年窗口
INITIAL_BACKFILL_DAYS = 3653

# 供应商正常应答但没有合格记录：这是"空数据"，不是"采集失败"
NO_DATA_REASON = "no_data"


class ValuationService:
    """理杏仁估值采集与读取（多指数 × 多指标）。"""

    def __init__(
        self,
        store: Store,
        token: str = "",
        calendar: TradingCalendar | Callable[[], TradingCalendar] | None = None,
        now_fn: Callable[[], datetime] | None = None,
        client_factory: Callable[[], Any] | None = None,
        retry_cooldown: timedelta = RETRY_COOLDOWN,
    ):
        self.store = store
        self._token = token or ""
        self._calendar = calendar
        self._now_fn = now_fn or (lambda: datetime.now(SHANGHAI_TZ))
        self._client_factory = client_factory or lx.new_client
        self._retry_cooldown = retry_cooldown
        # 采集入口（定时任务 / 启动 / 手动 / 周报）共用一把锁：
        # 串行执行"查缓存 → 请求 → 发布"，避免重叠执行重复发布或破坏状态。
        self._collect_lock = threading.Lock()

    # ---- 基础 ----
    def _now(self) -> datetime:
        """当前时间（统一为带时区的北京时间，naive 时间按北京时间解释）。"""
        value = self._now_fn()
        if value.tzinfo is None:
            return value.replace(tzinfo=SHANGHAI_TZ)
        return value

    def _calendar_instance(self) -> TradingCalendar:
        if callable(self._calendar) and not hasattr(self._calendar, "sessions"):
            return self._calendar()
        return self._calendar  # type: ignore[return-value]

    @property
    def enabled(self) -> bool:
        return bool(self._token)

    # ---- 目标日 ----
    def now_date(self) -> date:
        """当前北京时间自然日。"""
        return self._now().date()

    def resolve_daily_target_date(self) -> str | None:
        """最近一个已收盘交易日（页面与默认采集目标日）。

        15:05 收盘阈值之前取上一个交易日，之后可取当日；周末与节假日沿用
        最近一个已收盘交易日，绝不引用未来数据。

        日历不可用（越界）时返回 None——由调用方按 `calendar_unavailable`
        处理，不猜交易日。
        """
        now = self._now()
        # 回看窗口逐级缩短，避开日历覆盖起点（长假前一个交易日可能远在 10 天前）
        for lookback in (30, 15, 8, 3):
            try:
                calendar = self._calendar_instance()
                session = expected_last_session(calendar, now, lookback_days=lookback)
            except CalendarUnavailableError:
                continue
            if session is not None:
                return session.isoformat()
        return None

    def is_trading_day(self, day: date) -> bool:
        """交易日历确认某日是否交易日。

        日历不可用时抛 CalendarUnavailableError——调用方必须显式处理，
        绝不把"周一到周五"当成交易日。
        """
        calendar = self._calendar_instance()
        return bool(calendar.sessions(day, day))

    def resolve_week_target_date(self, week_start: str) -> str | None:
        """指定自然周的最后交易日（周报口径）。"""
        try:
            day = date.fromisoformat(week_start)
        except ValueError:
            return None
        return self._week_last_session(day)

    def resolve_last_trading_date(self, before: date) -> str | None:
        """before 之前最近一个交易日（休市周沿用最近有交易完整周的估值）。

        回看窗口逐级缩短，避开日历覆盖起点：长假前一个交易日可能远在 10 天前，
        但覆盖范围窄的日历只需要最近几天。
        """
        for lookback in (15, 8, 3):
            try:
                calendar = self._calendar_instance()
                sessions = calendar.sessions(
                    before - timedelta(days=lookback), before - timedelta(days=1)
                )
            except CalendarUnavailableError:
                continue
            if sessions:
                return sessions[-1].isoformat()
        return None

    def _week_last_session(self, week_start: date) -> str | None:
        try:
            calendar = self._calendar_instance()
            sessions = calendar.sessions(week_start, week_start + timedelta(days=6))
        except CalendarUnavailableError:
            return None
        return sessions[-1].isoformat() if sessions else None

    # ---- 状态快照 ----
    def _latest_row(self, index_code: str, metric: str, target_date: str | None) -> dict[str, Any] | None:
        return self.store.latest_valuation(
            index_code,
            lx.VALUATION_SOURCE,
            metric,
            lx.VALUATION_WINDOW,
            on_or_before=target_date,
        )

    def _metric_snapshot(
        self,
        state: str,
        reason: str | None,
        metric: str,
        target_date: str | None,
        row: dict[str, Any] | None,
    ) -> dict[str, Any]:
        ratio = row.get("percentile_ratio") if row else None
        value = row.get("value") if row else None
        return {
            "state": state,
            "reason": reason,
            "metric": metric,
            "source": lx.VALUATION_SOURCE,
            "window": lx.VALUATION_WINDOW,
            "target_date": target_date,
            "as_of": row.get("date") if row else None,
            "value": round(float(value), 2) if isinstance(value, (int, float)) else None,
            "percentile_pct": (
                round(float(ratio) * 100, 1) if isinstance(ratio, (int, float)) else None
            ),
            "captured_at": row.get("captured_at") if row else None,
        }

    def _metric_state(
        self,
        index_code: str,
        metric: str,
        target_date: str | None,
    ) -> tuple[str, str | None, dict[str, Any] | None]:
        """单个指标的状态判定。"""
        row = self._latest_row(index_code, metric, target_date)
        if not self.enabled:
            return STATE_DISABLED, "token_not_configured", row
        if target_date is None:
            return STATE_ERROR, "calendar_unavailable", row
        error = self._failed_for_target(index_code, metric, target_date)
        if error == NO_DATA_REASON:
            # 空数据不是错误：供应商照常应答，只是这条指标还没有值。
            # 若报成 error，页面会把"没有数据"误读成"采集坏了"。
            return STATE_EMPTY, NO_DATA_REASON, row
        if error:
            return STATE_ERROR, error, row
        if row is None:
            return STATE_EMPTY, None, row
        if row["date"] < target_date:
            return STATE_STALE, "not_updated_to_target", row
        return STATE_OK, None, row

    def status(
        self,
        target_date: str | None = None,
        *,
        index_code: str = DEFAULT_INDEX_CODE,
    ) -> dict[str, Any]:
        """只读本地缓存的状态（不请求供应商）。

        顶层保留 PE-TTM 的平铺字段（兼容既有页面），`metrics` 给出全部指标的完整状态。
        """
        if target_date is None:
            target_date = self.resolve_daily_target_date()
        metrics: dict[str, Any] = {}
        for metric in lx.VALUATION_METRIC_KEYS:
            state, reason, row = self._metric_state(index_code, metric, target_date)
            metrics[metric] = self._metric_snapshot(state, reason, metric, target_date, row)
        legacy = metrics[lx.VALUATION_METRIC]
        return {
            "index_code": index_code,
            "name": BY_CODE[index_code].name if index_code in BY_CODE else index_code,
            "state": legacy["state"],
            "reason": legacy["reason"],
            "source": legacy["source"],
            "metric": legacy["metric"],
            "window": legacy["window"],
            "target_date": target_date,
            "as_of": legacy["as_of"],
            "value": legacy["value"],
            # 兼容别名：旧页面与简报按 PE-TTM 的名字读这个数
            "pe_ttm": legacy["value"],
            "percentile_pct": legacy["percentile_pct"],
            "captured_at": legacy["captured_at"],
            "metrics": metrics,
        }

    # ---- 采集 ----
    def _fetch_start(self, index_code: str, metric: str, end_date: str) -> str:
        """本次请求的起点。

        已有数据时只补最近一段（30 天）并顺带补齐空档；一条都没有时回填
        整段 10 年，让分位走势图一开始就有历史。
        """
        end = date.fromisoformat(end_date)
        lookback_start = (end - timedelta(days=lx.LOOKBACK_DAYS)).isoformat()
        row = self.store.latest_valuation(
            index_code, lx.VALUATION_SOURCE, metric, lx.VALUATION_WINDOW
        )
        if row is None:
            return (end - timedelta(days=INITIAL_BACKFILL_DAYS)).isoformat()
        return min(row["date"], lookback_start)

    def refresh(
        self,
        target_date: str | None = None,
        *,
        index_code: str = DEFAULT_INDEX_CODE,
    ) -> dict[str, Any]:
        """尝试采集该指数的估值并返回状态快照。

        - 无 Token：不发请求，返回 disabled。
        - 所有指标同一目标日已有成功记录且无失败标记：跳过网络请求。
        - 失败后同一目标日进入冷却期（默认 15 分钟）；目标日变化不受旧冷却影响。
        - 失败保留既有合格数据，但状态不冒充 ok。
        - 采集全程串行：锁内重新查缓存，避免重叠执行重复请求或重复发布。
        """
        if not self.enabled:
            return self.status(target_date, index_code=index_code)
        if target_date is None:
            target_date = self.resolve_daily_target_date()
        if target_date is None:
            return self.status(None, index_code=index_code)

        with self._collect_lock:
            return self._refresh_locked(index_code, target_date)

    def _refresh_locked(self, index_code: str, target_date: str) -> dict[str, Any]:
        """锁内采集：查缓存 → 请求 → 发布（重入时缓存可能已被别的入口写好）。"""
        pending: list[str] = []
        for metric in lx.VALUATION_METRIC_KEYS:
            row = self._latest_row(index_code, metric, target_date)
            failed = self._failed_for_target(index_code, metric, target_date)
            if row and row["date"] == target_date and not failed:
                continue
            if failed and self._in_cooldown(index_code, metric):
                continue
            pending.append(metric)
        if not pending:
            return self.status(target_date, index_code=index_code)

        start_date = min(self._fetch_start(index_code, metric, target_date) for metric in pending)
        client = self._client_factory()
        try:
            points = lx.fetch_fundamental(
                client, self._token, index_code, target_date, start_date=start_date
            )
        except lx.LixingerError as exc:
            for metric in pending:
                self.store.record_valuation_failure(
                    index_code, metric, target_date, exc.reason, at=self._stamp()
                )
            return self.status(target_date, index_code=index_code)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        for metric in pending:
            series = [p for p in points if p.metric == metric]
            if not series:
                self.store.record_valuation_failure(
                    index_code, metric, target_date, "no_data", at=self._stamp()
                )
                continue
            self.store.publish_valuation(
                index_code,
                lx.VALUATION_SOURCE,
                metric,
                lx.VALUATION_WINDOW,
                [(p.date, p.value, p.percentile_ratio) for p in series],
                target_date,
                at=self._stamp(),
            )
        return self.status(target_date, index_code=index_code)

    def refresh_scheduled(self, index_code: str = DEFAULT_INDEX_CODE) -> dict[str, Any]:
        """定时采集入口（每日 18:30）。

        - 日历确认当日休市：跳过，不发任何请求。
        - 日历不可用：抛 CalendarUnavailableError（明确异常，不猜交易日）。
        - 其余情况：按最近已收盘交易日采集。
        """
        today = self.now_date()
        if not self.is_trading_day(today):
            return {
                "skipped": True,
                "reason": "not_trading_day",
                "date": today.isoformat(),
                "index_code": index_code,
            }
        target_date = self.resolve_daily_target_date()
        if target_date is None:
            raise CalendarUnavailableError(
                f"无法确定 {today.isoformat()} 之前最近一个已收盘交易日"
            )
        return self.refresh(target_date, index_code=index_code)

    def refresh_all(self) -> list[dict[str, Any]]:
        """按注册表顺序采集全部指数；单个指数失败不影响其他指数。"""
        results: list[dict[str, Any]] = []
        for code in index_codes():
            try:
                results.append(self.refresh(index_code=code))
            except Exception as exc:  # noqa: BLE001 — 单指数异常不阻断其他指数
                results.append({"index_code": code, "state": STATE_ERROR, "reason": str(exc)})
        return results

    # ---- 历史序列（分位走势图） ----
    def history(
        self,
        index_code: str,
        metric: str,
        start_date: str | None = None,
    ) -> dict[str, Any]:
        """一条指标的分位历史（日期升序），供分位走势图使用。"""
        rows = self.store.list_valuation_history(
            index_code, lx.VALUATION_SOURCE, metric, lx.VALUATION_WINDOW, start_date
        )
        return {
            "index_code": index_code,
            "metric": metric,
            "window": lx.VALUATION_WINDOW,
            "dates": [r["date"] for r in rows],
            "values": [r["value"] for r in rows],
            "percentiles": [
                None if r["percentile_ratio"] is None else round(r["percentile_ratio"] * 100, 1)
                for r in rows
            ],
        }

    def _failed_for_target(
        self, index_code: str, metric: str, target_date: str | None
    ) -> str | None:
        """最近一次采集失败的原因——只属于它自己的目标日与指标。

        失败只影响它被记录的那个目标日：别的目标日（更早的历史周报、
        更晚的页面目标日）按自己的数据判定状态，不拿旧失败说失败，
        也不拿新失败抹掉历史数据。
        """
        meta = self.store.get_valuation_meta(index_code, metric)
        error = meta.get("last_error") or None
        if not error or target_date is None:
            return None
        return error if meta.get("target_date") == target_date else None

    def _in_cooldown(self, index_code: str, metric: str) -> bool:
        meta = self.store.get_valuation_meta(index_code, metric)
        last_attempt = meta.get("last_attempt_at")
        if not last_attempt:
            return False
        try:
            attempted = datetime.fromisoformat(last_attempt)
        except ValueError:
            return False
        if attempted.tzinfo is None:
            attempted = attempted.replace(tzinfo=SHANGHAI_TZ)
        return self._now() - attempted < self._retry_cooldown

    def _stamp(self) -> str:
        """采集时间戳（业务时钟，北京时间）。"""
        return self._now().isoformat(timespec="seconds")

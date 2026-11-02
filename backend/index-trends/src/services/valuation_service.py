"""估值服务：理杏仁沪深300 PE-TTM 近 10 年分位。

职责边界：
- 本服务决定**目标日**（最近一个应当完成的自然周的最后交易日 / 指定周的最后交易日）、
  采集状态与缓存；不把估值混进趋势模型算法。
- 分位直接采用供应商统计值（0–1 的比例 → 0–100%），不在本地重新计算。
- 没有 Token 时正常启动并返回 disabled 状态；估值问题不阻断行情、图表与原周报。

对外统一对象：
    state: ok / stale / empty / error / disabled
    reason: 固定错误码（不含供应商正文与 Token）
    source / metric / window: 口径标识
    target_date: 期望的数据日期
    as_of: 实际数据日期
    pe_ttm / percentile_pct: 数值（缺失用 null，不用 0）
    captured_at: 采集时间
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from src.data import lixinger as lx
from src.data.trading_calendar import CalendarUnavailableError, TradingCalendar
from src.data.validate import expected_last_complete_week
from src.services.store import Store

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

INDEX_CODE = "000300"

STATE_OK = "ok"
STATE_STALE = "stale"
STATE_EMPTY = "empty"
STATE_ERROR = "error"
STATE_DISABLED = "disabled"

# 失败后的最小重试间隔（同一目标日）
RETRY_COOLDOWN = timedelta(minutes=15)


class ValuationService:
    """理杏仁估值采集与读取。"""

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
    def resolve_page_target_date(self) -> str | None:
        """页面目标日：最近一个应当完成的自然周的最后交易日。

        周五收盘（15:05）之后才切换到本周；进行中的周不取盘中或日频最新值。
        """
        try:
            calendar = self._calendar_instance()
            week_start = expected_last_complete_week(calendar, self._now())
        except CalendarUnavailableError:
            return None
        if week_start is None:
            return None
        return self._week_last_session(week_start)

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
    def _latest_row(self, target_date: str | None) -> dict[str, Any] | None:
        return self.store.latest_valuation(
            INDEX_CODE,
            lx.VALUATION_SOURCE,
            lx.VALUATION_METRIC,
            lx.VALUATION_WINDOW,
            on_or_before=target_date,
        )

    def _snapshot(
        self,
        state: str,
        reason: str | None,
        target_date: str | None,
        row: dict[str, Any] | None,
    ) -> dict[str, Any]:
        ratio = row.get("percentile_ratio") if row else None
        pe = row.get("pe_ttm") if row else None
        return {
            "state": state,
            "reason": reason,
            "source": lx.VALUATION_SOURCE,
            "metric": lx.VALUATION_METRIC,
            "window": lx.VALUATION_WINDOW,
            "target_date": target_date,
            "as_of": row.get("date") if row else None,
            "pe_ttm": round(float(pe), 2) if isinstance(pe, (int, float)) else None,
            "percentile_pct": round(float(ratio) * 100, 1) if isinstance(ratio, (int, float)) else None,
            "captured_at": row.get("captured_at") if row else None,
        }

    def status(self, target_date: str | None = None) -> dict[str, Any]:
        """只读本地缓存的状态（不请求供应商）。"""
        if target_date is None:
            target_date = self.resolve_page_target_date()
        row = self._latest_row(target_date)
        meta = self.store.get_valuation_meta()
        error = meta.get("last_error") or None
        if not self.enabled:
            return self._snapshot(STATE_DISABLED, "token_not_configured", target_date, row)
        if error:
            return self._snapshot(STATE_ERROR, error, target_date, row)
        if target_date is None:
            # 日历不可用：无法确定应该对齐哪个交易日，不把旧值当成目标周的新值
            return self._snapshot(STATE_ERROR, "calendar_unavailable", None, row)
        if row is None:
            return self._snapshot(STATE_EMPTY, None, target_date, None)
        if row["date"] < target_date:
            return self._snapshot(STATE_STALE, "not_updated_to_target", target_date, row)
        return self._snapshot(STATE_OK, None, target_date, row)

    # ---- 采集 ----
    def refresh(self, target_date: str | None = None) -> dict[str, Any]:
        """尝试采集估值并返回状态快照。

        - 无 Token：不发请求，返回 disabled。
        - 同一目标日已有成功记录且无失败标记：跳过网络请求。
        - 失败后同一目标日进入冷却期（默认 15 分钟）；目标日变化不受旧冷却影响。
        - 失败保留既有合格数据，但状态不冒充 ok。
        """
        if not self.enabled:
            return self.status(target_date)
        if target_date is None:
            target_date = self.resolve_page_target_date()
        if target_date is None:
            return self._snapshot(STATE_ERROR, "calendar_unavailable", None, None)

        row = self._latest_row(target_date)
        meta = self.store.get_valuation_meta()
        error = meta.get("last_error") or None
        if row and row["date"] == target_date and not error:
            return self._snapshot(STATE_OK, None, target_date, row)
        if error and meta.get("target_date") == target_date and self._in_cooldown(meta):
            return self._snapshot(STATE_ERROR, error, target_date, row)

        client = self._client_factory()
        try:
            points = lx.fetch_fundamental(client, self._token, INDEX_CODE, target_date)
        except lx.LixingerError as exc:
            self.store.record_valuation_failure(INDEX_CODE, target_date, exc.reason)
            return self._snapshot(STATE_ERROR, exc.reason, target_date, row)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        selected = lx.latest_qualified(points, target_date)
        if selected is None:
            self.store.record_valuation_failure(INDEX_CODE, target_date, "no_data")
            return self._snapshot(STATE_EMPTY, "no_data", target_date, row)

        self.store.publish_valuation(
            INDEX_CODE,
            lx.VALUATION_SOURCE,
            lx.VALUATION_METRIC,
            lx.VALUATION_WINDOW,
            [(p.date, p.pe_ttm, p.percentile_ratio) for p in points],
            target_date,
        )
        return self.status(target_date)

    def _in_cooldown(self, meta: dict[str, Any]) -> bool:
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

"""估值服务：理杏仁沪深300 PE-TTM 近 10 年分位。

职责边界：
- 本服务决定**目标日**（页面与每日采集：最近一个已收盘交易日）、采集状态与缓存；
不把估值混进趋势模型算法。
- 分位直接采用供应商统计值（0–1 的比例 → 0–100%），不在本地重新计算。
- 没有 Token 时正常启动并返回 disabled 状态；估值问题不阻断行情、图表与查询。

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

import threading
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from src.data import lixinger as lx
from src.data.trading_calendar import CalendarUnavailableError, TradingCalendar
from src.data.validate import expected_last_session
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
            target_date = self.resolve_daily_target_date()
        row = self._latest_row(target_date)
        meta = self.store.get_valuation_meta()
        error = self._failed_for_target(meta, target_date)
        if not self.enabled:
            return self._snapshot(STATE_DISABLED, "token_not_configured", target_date, row)
        if target_date is None:
            # 日历不可用：无法确定应该对齐哪个交易日，不把旧值当成当日的新值
            return self._snapshot(STATE_ERROR, "calendar_unavailable", None, row)
        if error:
            return self._snapshot(STATE_ERROR, error, target_date, row)
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
        - 采集全程串行：锁内重新查缓存，避免重叠执行重复请求或重复发布。
        """
        if not self.enabled:
            return self.status(target_date)
        if target_date is None:
            target_date = self.resolve_daily_target_date()
        if target_date is None:
            return self._snapshot(STATE_ERROR, "calendar_unavailable", None, None)

        with self._collect_lock:
            return self._refresh_locked(target_date)

    def _refresh_locked(self, target_date: str) -> dict[str, Any]:
        """锁内采集：查缓存 → 请求 → 发布（重入时缓存可能已被别的入口写好）。"""
        row = self._latest_row(target_date)
        meta = self.store.get_valuation_meta()
        failed = self._failed_for_target(meta, target_date)
        if row and row["date"] == target_date and not failed:
            return self._snapshot(STATE_OK, None, target_date, row)
        if failed and self._in_cooldown(meta):
            return self._snapshot(STATE_ERROR, failed, target_date, row)

        client = self._client_factory()
        try:
            points = lx.fetch_fundamental(client, self._token, INDEX_CODE, target_date)
        except lx.LixingerError as exc:
            self.store.record_valuation_failure(
                INDEX_CODE, target_date, exc.reason, at=self._stamp()
            )
            return self._snapshot(STATE_ERROR, exc.reason, target_date, row)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        selected = lx.latest_qualified(points, target_date)
        if selected is None:
            self.store.record_valuation_failure(
                INDEX_CODE, target_date, "no_data", at=self._stamp()
            )
            return self._snapshot(STATE_EMPTY, "no_data", target_date, row)

        self.store.publish_valuation(
            INDEX_CODE,
            lx.VALUATION_SOURCE,
            lx.VALUATION_METRIC,
            lx.VALUATION_WINDOW,
            [(p.date, p.pe_ttm, p.percentile_ratio) for p in points],
            target_date,
            at=self._stamp(),
        )
        return self.status(target_date)

    def refresh_scheduled(self) -> dict[str, Any]:
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
            }
        target_date = self.resolve_daily_target_date()
        if target_date is None:
            raise CalendarUnavailableError(
                f"无法确定 {today.isoformat()} 之前最近一个已收盘交易日"
            )
        return self.refresh(target_date)

    def _failed_for_target(self, meta: dict[str, Any], target_date: str | None) -> str | None:
        """最近一次采集失败的原因——只属于它自己的目标日。

        失败只影响它被记录的那个目标日：别的目标日（更早的历史周报、
        更晚的页面目标日）按自己的数据判定状态，不拿旧失败说失败，
        也不拿新失败抹掉历史数据。
        """
        error = meta.get("last_error") or None
        if not error or target_date is None:
            return None
        return error if meta.get("target_date") == target_date else None

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

    def _stamp(self) -> str:
        """采集时间戳（业务时钟，北京时间）。"""
        return self._now().isoformat(timespec="seconds")

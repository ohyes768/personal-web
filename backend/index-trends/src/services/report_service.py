"""每周摘要服务（周线口径）。

幂等与状态约定：
- 幂等键 = 指数|ISO自然周|weekly。同一周已 sent 的报告（含旧月线）不会被重发。
- 未配置渠道时报告保存为 no_channel，不伪报送达；之后手动触发可重试。
- 交易周在日历确认的最后交易日 15:05 之后才算完成。此前的手动触发
  不写正常最终周报，避免占掉本周去重投递机会。
- 只有日历确认全周无交易才记 no_trading。缺行情、日历越界、缺模型都是
  data_error，不能写成休市或 normal。
- 周报模型来自持久化配置（月线 kind 只在读取时映射为周线），页面临时选择不写配置。
- 位置变化只和同一周线 kind 的上周快照比较，并拆成价格 / 模型 / 时间推进。
  旧月线位置不当作上周周线位置。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.core.models import (
    CURRENT_WEEKLY_MODEL_KINDS,
    KIND_TRAILING_WEEKLY,
    LEGACY_KIND_TO_WEEKLY,
    REGION_LABELS_ZH,
    classify_region,
)
from src.core.regression import Coefficients
from src.core.weekly import project_week
from src.core.weeks import iso_week_label, week_start_of
from src.data.trading_calendar import CalendarUnavailableError
from src.data.validate import CLOSE_TOLERANCE, MARKET_CLOSE_CUTOFF
from src.services.notifier import DingTalkNotifier
from src.services.store import Store
from src.services.trend_service import INDEX_CODE, INDEX_NAME, WeeklyTrendService
from src.services.valuation_service import ValuationService

REPORT_KIND = "weekly"
REPORT_PAGE_PATH = "/index-trends?tab=current"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def current_iso_week(now: datetime) -> str:
    return iso_week_label(now.date())


def previous_iso_week(now: datetime) -> str:
    """上一自然周的 ISO 周标签。

    从本周一回退 7 天，跨年周按 ISO 规则归属（例如 2027-W01 的上一周是 2026-W53）。
    """
    previous_monday = week_start_of(now.date()) - timedelta(days=7)
    return iso_week_label(previous_monday)


def idempotency_key(index_code: str, iso_week: str) -> str:
    return f"{index_code}|{iso_week}|{REPORT_KIND}"


def position_change_components(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, float]:
    """把位置变化拆成价格、模型与时间推进。三项之和等于新旧位置之差。

    previous / current 都是周线快照：含 timeframe、fit_start、multiplier、
    coefficients、close、projection_week。
    """
    previous_at_prev = _project_snapshot(previous, previous["close"], previous["projection_week"])
    previous_at_curr = _project_snapshot(previous, previous["close"], current["projection_week"])
    current_on_prev = _project_snapshot(previous, current["close"], current["projection_week"])
    current_at_curr = _project_snapshot(current, current["close"], current["projection_week"])
    price_impact = current_on_prev - previous_at_curr
    model_impact = current_at_curr - current_on_prev
    time_impact = previous_at_curr - previous_at_prev
    total = current_at_curr - previous_at_prev
    return {
        "price_impact": price_impact,
        "model_impact": model_impact,
        "time_impact": time_impact,
        "total": total,
        "current_position": current_at_curr,
        "previous_position": previous_at_prev,
    }


def _project_snapshot(snapshot: dict[str, Any], close: float, week_start: str) -> float:
    coeff = snapshot["coefficients"]
    coefficients = Coefficients(coeff["slope"], coeff["intercept"], coeff["deviation"])
    _mid, _upper, _lower, pct = project_week(
        coefficients, float(snapshot["multiplier"]), snapshot["fit_start"], week_start, close
    )
    return pct


def _is_weekly_snapshot(report: dict[str, Any]) -> bool:
    raw = report.get("snapshot_json")
    if not raw:
        return False
    try:
        snapshot = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return False
    return (
        isinstance(snapshot, dict)
        and snapshot.get("timeframe") == "week"
        and isinstance(snapshot.get("coefficients"), dict)
        and snapshot.get("fit_start")
        and snapshot.get("projection_week")
        and snapshot.get("close") is not None
    )


class ReportService:
    def __init__(
        self,
        store: Store,
        trend_service: WeeklyTrendService,
        notifier: DingTalkNotifier,
        public_url: str = "",
        now_fn: Any | None = None,
        valuation_service: ValuationService | None = None,
    ):
        self.store = store
        self.trend_service = trend_service
        self.notifier = notifier
        self.public_url = public_url.rstrip("/")
        self._now_fn = now_fn or (lambda: datetime.now(SHANGHAI_TZ))
        self.valuation_service = valuation_service

    def _now(self) -> datetime:
        return self._now_fn()

    def run_weekly_sync(self, manual: bool = False) -> dict[str, Any]:
        """生成并发送本周摘要（同步实现；调用方负责持有刷新锁）。"""
        now = self._now()
        iso_week = current_iso_week(now)
        key = idempotency_key(INDEX_CODE, iso_week)
        settings = self.store.get_report_settings()

        existing = self.store.get_report(key)
        if existing and existing["status"] == "sent":
            return {"skipped": True, "reason": "already_sent", "iso_week": iso_week}
        if not settings.get("enabled") and not manual:
            return {"skipped": True, "reason": "disabled", "iso_week": iso_week}

        week_state = self._week_trading_state(now)
        if week_state == "incomplete":
            # 先刷新可以更新进行中周的展示数据，但不占用本周最终投递名额。
            self._refresh()
            return {"skipped": True, "reason": "week_incomplete", "iso_week": iso_week}

        refresh_error = self._refresh()
        model_kind = self._configured_kind(settings)
        return self._generate_and_send(key, iso_week, model_kind, now, week_state, refresh_error)

    def _refresh(self) -> str | None:
        try:
            result = self.trend_service.refresh_sync()
            if not getattr(result, "success", True):
                return getattr(result, "message", None) or "刷新未成功"
            return None
        except Exception as exc:  # noqa: BLE001 — 供应商异常要出现在摘要里
            return str(exc)

    def _configured_kind(self, settings: dict[str, Any]) -> str:
        raw = settings.get("model_kind") or KIND_TRAILING_WEEKLY
        mapped = LEGACY_KIND_TO_WEEKLY.get(raw, raw)
        if mapped not in CURRENT_WEEKLY_MODEL_KINDS:
            return KIND_TRAILING_WEEKLY
        return mapped

    def _week_trading_state(self, now: datetime) -> str:
        """complete | incomplete | no_trading | calendar_unavailable。"""
        monday = week_start_of(now.date())
        sunday = monday + timedelta(days=6)
        try:
            sessions = self.trend_service.trading_calendar().sessions(monday, sunday)
        except CalendarUnavailableError:
            return "calendar_unavailable"
        if not sessions:
            return "no_trading"
        last = sessions[-1]
        cutoff = datetime.combine(last, MARKET_CLOSE_CUTOFF, tzinfo=now.tzinfo)
        if now >= cutoff:
            return "complete"
        return "incomplete"

    def _generate_and_send(
        self,
        key: str,
        iso_week: str,
        model_kind: str,
        now: datetime,
        week_state: str,
        refresh_error: str | None,
    ) -> dict[str, Any]:
        built = self._build_report(iso_week, model_kind, now, week_state, refresh_error)
        existing = self.store.get_report(key)
        if existing and existing["status"] != "sent":
            self.store.archive_report_attempt(
                key,
                model_id=existing.get("model_id"),
                model_kind=existing.get("model_kind"),
                business_status=existing.get("business_status"),
                status=existing.get("status"),
                error=existing.get("error"),
                snapshot_json=existing.get("snapshot_json"),
                payload=existing.get("content"),
            )

        report = {
            "idempotency_key": key,
            "index_code": INDEX_CODE,
            "iso_week": iso_week,
            "model_id": built["model_id"],
            "model_kind": model_kind,
            "business_status": built["business_status"],
            "close": built["close"],
            "close_date": built["close_date"],
            "region": built["region"],
            "position_pct": built["position_pct"],
            "content": built["content"],
            "status": "pending",
            "error": built["error"],
            "snapshot_json": built["snapshot_json"],
        }
        self.store.upsert_report(report)

        ok, err = self.notifier.send_markdown(f"宽基趋势观察 {iso_week}", built["content"])
        if ok:
            self.store.mark_report_sent(key, "sent")
            final_status, final_error = "sent", None
        else:
            final_status = "no_channel" if err == "channel_not_configured" else "failed"
            final_error = err
            self.store.mark_report_sent(key, final_status, err)
        self.store.archive_report_attempt(
            key,
            model_id=built["model_id"],
            model_kind=model_kind,
            business_status=built["business_status"],
            status=final_status,
            error=final_error,
            snapshot_json=built["snapshot_json"],
            payload=built["content"],
        )
        outcome: dict[str, Any] = {
            "sent": ok,
            "status": final_status,
            "business_status": built["business_status"],
            "iso_week": iso_week,
        }
        if not ok:
            outcome["error"] = final_error
        return outcome

    def _build_report(
        self,
        iso_week: str,
        model_kind: str,
        now: datetime,
        week_state: str,
        refresh_error: str | None,
    ) -> dict[str, Any]:
        kind_label = "近10年" if model_kind == KIND_TRAILING_WEEKLY else "成立以来"
        if refresh_error or week_state == "calendar_unavailable":
            reason = refresh_error or "交易日历超出覆盖范围"
            return self._error_report(
                kind_label,
                "data_error",
                reason,
                [
                    "**数据异常**：本周摘要无法基于有效数据生成。",
                    "",
                    f"> 错误：{reason}",
                    "",
                    "> 缺失行情、日历不可用与整周休市是不同情况；这里不是休市说明。",
                ],
            )
        if week_state == "no_trading":
            valuation = self._valuation_readonly(self._holiday_valuation_target(now))
            content = self._join(
                kind_label,
                [
                    f"**{iso_week} 全周休市**：交易日历确认本周无交易日，无新收盘数据。",
                    "",
                    self._valuation_line(valuation, holiday=True),
                    "",
                    "> 每周照常提醒 · 本周无交易变化",
                ],
            )
            return {
                "business_status": "no_trading",
                "model_id": self._model_id_of(model_kind),
                "close": None,
                "close_date": None,
                "region": None,
                "position_pct": None,
                "content": content,
                "error": None,
                "snapshot_json": None,
            }

        monday = week_start_of(now.date()).isoformat()
        bars = self.store.load_weekly_bars(include_partial=False)
        bar = bars.get(monday)
        if bar is None:
            return self._error_report(
                kind_label,
                "data_error",
                "missing_weekly_bar",
                [
                    f"**数据异常**：日历确认 {monday} 当周应有收盘，但周K缺失。",
                    "",
                    "> 这不是休市。休市只在日历确认全周无交易时成立。",
                ],
            )
        dailies = {item.date: item.close for item in self.store.load_daily_quotes(limit=400)}
        daily_close = dailies.get(bar.date)
        if daily_close is None or abs(daily_close - bar.close) > CLOSE_TOLERANCE:
            return self._error_report(
                kind_label,
                "data_error",
                "weekly_daily_mismatch",
                [
                    f"**数据异常**：周K收盘（{bar.date} {bar.close:.2f}）与当日日线不一致或日线缺失。",
                    "",
                    "> 不能把缺失行情写成休市或正常摘要。",
                ],
            )

        model = self.store.latest_weekly_model(INDEX_CODE, model_kind)
        if model is None:
            return self._error_report(
                kind_label,
                "data_error",
                "model_not_ready",
                ["**模型不可用**：缺少周线通道模型，本周不能生成正常摘要。"],
            )

        try:
            mid, upper, lower, pct = project_week(
                model.coefficients, model.multiplier, model.fit_start, monday, bar.close
            )
        except ValueError as exc:
            return self._error_report(
                kind_label,
                "data_error",
                str(exc),
                [f"**模型不可用**：通道无效（{exc}），本周不能生成正常摘要。"],
            )
        region = classify_region(pct)
        meta = self.store.get_weekly_data_meta()
        snapshot = {
            "timeframe": "week",
            "model_id": model.model_id,
            "model_kind": model.kind,
            "fit_start": model.fit_start,
            "fit_end": model.fit_end,
            "sample_count": model.sample_count,
            "algorithm_version": model.algorithm_version,
            "multiplier": model.multiplier,
            "coefficients": {
                "slope": model.coefficients.slope,
                "intercept": model.coefficients.intercept,
                "deviation": model.coefficients.deviation,
            },
            "close": bar.close,
            "close_date": bar.date,
            "projection_week": monday,
            "position_pct": pct,
            "region": region,
            "upper": upper,
            "mid": mid,
            "lower": lower,
            "snapshot_id": meta.get("snapshot_id"),
        }
        comparison = self._comparison_lines(iso_week, model_kind, snapshot, now)
        price_change = self._price_change_line(bars, monday, bar.close)
        valuation = self._valuation_snapshot(bar.date)
        snapshot["valuation"] = valuation
        lines = [
            f"- 收盘（{bar.date}）：**{bar.close:.2f}**",
            f"- 周涨跌：{price_change}",
            f"- 通道位置：**{pct:.1f}%**，区域：**{REGION_LABELS_ZH[region]}**",
            f"- 上/中/下轨：{upper:.2f} / {mid:.2f} / {lower:.2f}",
            self._valuation_line(valuation),
            (
                f"- 模型区间：{model.fit_start} 至 {model.fit_end}"
                f"（{kind_label}，{model.sample_count} 个交易周，{model.algorithm_version}）"
            ),
            f"- 投影周：{monday} · 快照 {meta.get('snapshot_id') or '未编号'}",
            "",
            "> 区域描述指数相对趋势通道的位置，不构成买卖建议。延伸线是趋势参考，不是目标价。",
            *comparison,
        ]
        return {
            "business_status": "normal",
            "model_id": model.model_id,
            "close": bar.close,
            "close_date": bar.date,
            "region": region,
            "position_pct": round(pct, 2),
            "content": self._join(kind_label, lines),
            "error": None,
            "snapshot_json": json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        }

    def _valuation_snapshot(self, target_date: str | None) -> dict[str, Any] | None:
        """取报告发送时的估值（尽力而为；异常不改变周报状态与投递结果）。"""
        if self.valuation_service is None:
            return None
        try:
            return self.valuation_service.refresh(target_date)
        except Exception:  # noqa: BLE001 — 估值异常只影响估值行
            try:
                return self.valuation_service.status(target_date)
            except Exception:  # noqa: BLE001
                return None

    def _holiday_valuation_target(self, now: datetime) -> str | None:
        """休市周的估值目标日：最近一个交易日的估值（明确“沿用”）。"""
        if self.valuation_service is None:
            return None
        monday = week_start_of(now.date())
        return self.valuation_service.resolve_last_trading_date(monday)

    def _valuation_readonly(self, target_date: str | None = None) -> dict[str, Any] | None:
        """只读缓存的估值（休市等不需要新数据的场景）。"""
        if self.valuation_service is None:
            return None
        try:
            return self.valuation_service.status(target_date)
        except Exception:  # noqa: BLE001
            return None

    def _valuation_line(self, valuation: dict[str, Any] | None, holiday: bool = False) -> str:
        """把估值状态渲染成一行周报文案（与通道位置严格区分）。"""
        if valuation is None:
            return "- 估值：暂不可用"
        state = valuation.get("state")
        pct = valuation.get("percentile_pct")
        pe = valuation.get("pe_ttm")
        as_of = valuation.get("as_of")
        target = valuation.get("target_date")
        if state == "ok" and pct is not None:
            tail = "（休市沿用最近有交易完整周）" if holiday else ""
            return (
                f"- 估值（沪深300 PE-TTM 近10年分位）：**{pct:.1f}%**，"
                f"PE {pe:.2f}（数据日期 {as_of}，总市值加权，理杏仁）{tail}"
            )
        if state == "stale" and pct is not None:
            return (
                f"- 估值（沪深300 PE-TTM 近10年分位）：{pct:.1f}%，PE {pe:.2f}"
                f"（数据日期 {as_of}，未更新至 {target}，理杏仁）"
            )
        if state == "disabled":
            return "- 估值：暂不可用（未配置理杏仁访问令牌）"
        if state == "empty":
            return "- 估值：暂不可用（暂无估值数据）"
        reason = valuation.get("reason") or "unknown"
        return f"- 估值：暂不可用（{reason}）"

    def _error_report(
        self,
        kind_label: str,
        business_status: str,
        error: str,
        lines: list[str],
    ) -> dict[str, Any]:
        return {
            "business_status": business_status,
            "model_id": "unavailable",
            "close": None,
            "close_date": None,
            "region": None,
            "position_pct": None,
            "content": self._join(kind_label, lines),
            "error": error,
            "snapshot_json": None,
        }

    def _model_id_of(self, model_kind: str) -> str:
        model = self.store.latest_weekly_model(INDEX_CODE, model_kind)
        return model.model_id if model else "unavailable"

    def _price_change_line(self, bars: dict[str, Any], monday: str, close: float) -> str:
        earlier = [week for week in sorted(bars) if week < monday]
        if not earlier:
            return "不可比较（没有更早的有交易周）"
        previous = bars[earlier[-1]]
        change = close / previous.close - 1
        return (
            f"{change * 100:+.2f}%（比较基期 {previous.date} 收盘 {previous.close:.2f}）"
        )

    def _comparison_lines(
        self,
        iso_week: str,
        model_kind: str,
        current: dict[str, Any],
        now: datetime,
    ) -> list[str]:
        """只和紧邻的上一自然周、同一周线 kind 的快照比较。

        更早的周线快照不能冒充“上周”：中间隔周时，时间推进会被算进错误的一周。
        上一周若是旧月线报告，也不能拿它的位置来比较。
        """
        previous_key = idempotency_key(INDEX_CODE, previous_iso_week(now))
        previous_report = self.store.get_report(previous_key)
        if (
            previous_report
            and previous_report.get("model_kind") == model_kind
            and _is_weekly_snapshot(previous_report)
        ):
            previous = json.loads(previous_report["snapshot_json"])
            if previous.get("timeframe") != "week":
                return ["> 位置变化：不可比较（跨周期，不能把月线位置当作上周周线位置）。"]
            try:
                parts = position_change_components(previous, current)
            except (KeyError, TypeError, ValueError):
                return ["> 位置变化：不可比较（旧快照缺少可复算的系数）。"]
            return [
                (
                    "> 与上周周线快照相比："
                    f"合计 {parts['total']:+.2f} 个百分点"
                    f"（价格影响 {parts['price_impact']:+.2f}，"
                    f"模型影响 {parts['model_impact']:+.2f}，"
                    f"时间推进 {parts['time_impact']:+.2f}）。"
                )
            ]

        reports = self.store.list_reports(limit=80)
        older_weekly = [
            item
            for item in reports
            if item.get("iso_week", "") < iso_week
            and item.get("model_kind") == model_kind
            and _is_weekly_snapshot(item)
        ]
        monthly_rows = [
            item
            for item in reports
            if item.get("model_kind") in LEGACY_KIND_TO_WEEKLY and item.get("iso_week", "") <= iso_week
        ]
        if monthly_rows and not older_weekly:
            return ["> 位置变化：不可比较（首次周线报告不与旧月线位置比较）。"]
        if previous_report:
            return ["> 位置变化：不可比较（上一周没有同周期可复算的周线快照）。"]
        return ["> 位置变化：不可比较（没有上一周的同周期周线快照）。"]

    def _join(self, kind_label: str, lines: list[str]) -> str:
        head = [f"## 宽基趋势观察 · {INDEX_NAME}（{kind_label}模型）", ""]
        if self.public_url:
            lines = [*lines, "", f"[查看当前通道]({self.public_url}{REPORT_PAGE_PATH})"]
        return "\n".join(head + lines)

    def catchup_if_needed(self) -> dict[str, Any] | None:
        """启动补发检查：已过本周五 19:00 且本周报告未 sent → 补跑（幂等保护）。"""
        now = self._now()
        monday = week_start_of(now.date())
        friday = monday + timedelta(days=4)
        friday_19 = datetime(friday.year, friday.month, friday.day, 19, 0, tzinfo=SHANGHAI_TZ)
        if now < friday_19:
            return None
        key = idempotency_key(INDEX_CODE, current_iso_week(now))
        existing = self.store.get_report(key)
        if existing and existing["status"] == "sent":
            return None
        return self.run_weekly_sync(manual=False)

"""每周摘要服务。

幂等与状态约定（R5/AC7）：
- 幂等键 = 指数|ISO自然周|weekly；同一周已 sent 的报告不会被重复发送。
- 未配置渠道时报告保存为 no_channel，不发送也不伪报成功；后续手动触发可重试发送。
- 周五休市取当周最后交易日收盘；整周休市生成 no_trading 说明记录。
- 周报模型来自持久化配置，与页面临时选择完全分离；报告记录 model_id，
  月度重算换模型版本时与价格变化区分展示。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.core import months as mutils
from src.core.models import (
    KIND_TRAILING,
    REGION_LABELS_ZH,
    classify_region,
    position_pct,
)
from src.core.regression import channel_at
from src.data.validate import to_month_key
from src.services.notifier import DingTalkNotifier
from src.services.store import Store
from src.services.trend_service import INDEX_CODE, INDEX_NAME, SHANGHAI_TZ, TrendService

REPORT_KIND = "weekly"
REPORT_PAGE_PATH = "/index-trends?tab=current"


def current_iso_week(now: datetime) -> str:
    (year, week, _) = now.isocalendar()
    return f"{year}-W{week:02d}"


def idempotency_key(index_code: str, iso_week: str) -> str:
    return f"{index_code}|{iso_week}|{REPORT_KIND}"


class ReportService:
    def __init__(self, store: Store, trend_service: TrendService, notifier: DingTalkNotifier, public_url: str = ""):
        self.store = store
        self.trend_service = trend_service
        self.notifier = notifier
        self.public_url = public_url.rstrip("/")

    def _now(self) -> datetime:
        return datetime.now(SHANGHAI_TZ)

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

        # 刷新数据：失败不阻塞报告，但状态如实标注
        refresh_error: str | None = None
        try:
            result = self.trend_service.refresh_sync()
            if not result.success:
                refresh_error = result.message
        except Exception as e:  # noqa: BLE001 — 供应商异常要出现在摘要里，不能中断
            refresh_error = str(e)

        model_kind = settings.get("model_kind") or KIND_TRAILING
        week_close = self._week_last_close(now)
        return self._generate_and_send(key, iso_week, model_kind, week_close, refresh_error)

    def _week_last_close(self, now: datetime) -> dict[str, Any] | None:
        """当周最后交易日收盘（周报口径）。整周休市返回 None。"""
        monday = (now - timedelta(days=now.isoweekday() - 1)).date()
        week_start = monday.isoformat()
        week_end = (monday + timedelta(days=6)).isoformat()
        for bar in self.store.load_daily_quotes(limit=100):
            if week_start <= bar.date <= week_end:
                return {"date": bar.date, "close": bar.close}
        return None

    def _generate_and_send(
        self,
        key: str,
        iso_week: str,
        model_kind: str,
        week_close: dict[str, Any] | None,
        refresh_error: str | None,
    ) -> dict[str, Any]:
        """status 只记投递结果（sent/no_channel/failed）；内容状态记 business_status。"""
        business = "data_error" if refresh_error else ("no_trading" if week_close is None else "normal")
        content = self._render(iso_week, model_kind, week_close, refresh_error)

        report: dict[str, Any] = {
            "idempotency_key": key,
            "index_code": INDEX_CODE,
            "iso_week": iso_week,
            "model_id": self._model_id_of(model_kind),
            "model_kind": model_kind,
            "business_status": business,
            "close": week_close["close"] if week_close else None,
            "close_date": week_close["date"] if week_close else None,
            "region": self._region_of(model_kind, week_close),
            "position_pct": self._position_of(model_kind, week_close),
            "content": content,
            "status": "pending",
            "error": refresh_error,
        }
        self.store.upsert_report(report)

        # 发送：无论区域是否变化每周都发（含休市说明与数据异常摘要）；
        # 渠道未配置 → no_channel 如实保存，不伪报成功
        ok, err = self.notifier.send_markdown(f"宽基趋势观察 {iso_week}", content)
        if ok:
            self.store.mark_report_sent(key, "sent")
            return {"sent": True, "status": "sent", "business_status": business, "iso_week": iso_week}
        final_status = "no_channel" if err == "channel_not_configured" else "failed"
        self.store.mark_report_sent(key, final_status, err)
        return {"sent": False, "status": final_status, "business_status": business, "iso_week": iso_week, "error": err}

    def _model_id_of(self, model_kind: str) -> str:
        model = self.store.latest_model(INDEX_CODE, model_kind)
        return model.model_id if model else "unavailable"

    def _projection(self, model_kind: str, close: float, close_date: str) -> dict[str, Any] | None:
        model = self.store.latest_model(INDEX_CODE, model_kind)
        if model is None:
            return None
        proj_month = to_month_key(close_date)
        x = mutils.month_sequence_index(proj_month, model.fit_start)
        mid, upper, lower = channel_at(model.coefficients, x, model.multiplier)
        try:
            pct = position_pct(close, upper, lower)
        except ValueError:
            return None
        return {
            "upper": upper,
            "mid": mid,
            "lower": lower,
            "position_pct": pct,
            "region": classify_region(pct),
            "fit_start": model.fit_start,
            "fit_end": model.fit_end,
        }

    def _region_of(self, model_kind: str, week_close: dict[str, Any] | None) -> str | None:
        if not week_close:
            return None
        proj = self._projection(model_kind, week_close["close"], week_close["date"])
        return proj["region"] if proj else None

    def _position_of(self, model_kind: str, week_close: dict[str, Any] | None) -> float | None:
        if not week_close:
            return None
        proj = self._projection(model_kind, week_close["close"], week_close["date"])
        return round(proj["position_pct"], 2) if proj else None

    def _render(
        self,
        iso_week: str,
        model_kind: str,
        week_close: dict[str, Any] | None,
        refresh_error: str | None,
    ) -> str:
        kind_label = "近10年" if model_kind == KIND_TRAILING else "成立以来"
        lines = [f"## 宽基趋势观察 · {INDEX_NAME}（{kind_label}模型）", ""]
        if refresh_error:
            lines += [
                f"**数据异常**：本周摘要无法基于有效数据生成。",
                "",
                f"> 错误：{refresh_error}",
            ]
            return "\n".join(lines)
        if week_close is None:
            lines += [
                f"**{iso_week} 全周休市**：本周无交易日，无新收盘数据。",
                "",
                "> 每周照常提醒 · 本周无交易变化",
            ]
            return "\n".join(lines)
        proj = self._projection(model_kind, week_close["close"], week_close["date"])
        if proj is None:
            lines += ["**模型不可用**：无法计算通道位置，请检查数据。"]
            return "\n".join(lines)
        region_label = REGION_LABELS_ZH[proj["region"]]
        lines += [
            f"- 收盘（{week_close['date']}）：**{week_close['close']:.2f}**",
            f"- 通道位置：**{proj['position_pct']:.1f}%**，区域：**{region_label}**",
            f"- 上/中/下轨：{proj['upper']:.0f} / {proj['mid']:.0f} / {proj['lower']:.0f}",
            f"- 模型区间：{proj['fit_start']} 至 {proj['fit_end']}（{kind_label}，120个月拟合）"
            if model_kind == KIND_TRAILING
            else f"- 模型区间：{proj['fit_start']} 至 {proj['fit_end']}（成立以来全样本）",
            "",
            "> 区域描述指数相对趋势通道的位置，不构成买卖建议。",
        ]
        prev = self._previous_report_context(iso_week, model_kind)
        if prev:
            lines += [f"> 与上周对比：上周位置 {prev['position_pct']:.1f}%（{REGION_LABELS_ZH[prev['region']]}）。" + (
                "模型于本月完成月度重算，版本已更新。" if prev["model_id"] != self._model_id_of(model_kind) else ""
            )]
        if self.public_url:
            lines += ["", f"[查看当前通道]({self.public_url}{REPORT_PAGE_PATH})"]
        return "\n".join(lines)

    def _previous_report_context(self, iso_week: str, model_kind: str) -> dict[str, Any] | None:
        reports = self.store.list_reports(limit=20)
        for r in reports:
            if r["iso_week"] < iso_week and r["model_kind"] == model_kind and r["position_pct"] is not None:
                return r
        return None

    def catchup_if_needed(self) -> dict[str, Any] | None:
        """启动补发检查：已过本周五 19:00 且本周报告未 sent → 补跑（幂等保护）。"""
        now = self._now()
        monday = (now - timedelta(days=now.isoweekday() - 1)).date()
        friday = monday + timedelta(days=4)
        friday_19 = datetime(friday.year, friday.month, friday.day, 19, 0, tzinfo=SHANGHAI_TZ)
        if now < friday_19:
            return None
        key = idempotency_key(INDEX_CODE, current_iso_week(now))
        existing = self.store.get_report(key)
        if existing and existing["status"] == "sent":
            return None
        return self.run_weekly_sync(manual=False)

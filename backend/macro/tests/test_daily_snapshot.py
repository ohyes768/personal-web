"""日频快照服务测试

覆盖:默认日期 15:00 规则、显式日期取值、无值日期 asof 回退 + data_date 标注、
dates 列表构造、volume 无数据兜底、路由层非法日期 400。
"""
import os
from datetime import datetime
from pathlib import Path

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

import pandas as pd
import pytest
from fastapi import HTTPException

from src.services import data_service as ds_mod
from src.services.data_service import DataService
from src.services.daily_snapshot_service import DailySnapshotService

# 固定测试交易日(升序):volume 每 A股交易日必有值
DATES = ["2026-08-25", "2026-08-26", "2026-08-27"]


def _make_service(tmp_path: Path) -> DataService:
    """指向 tmp_path 的 DataService,并清空 query 缓存(与 test_query_data_by_tab 同款)"""
    service = DataService()
    service.data_dir = tmp_path
    service.files = {key: tmp_path / path.name for key, path in service.files.items()}
    with ds_mod._QUERY_CACHE_LOCK:
        ds_mod._QUERY_CACHE.clear()
    ds_mod._bump_cache_version()
    return service


def _write_csv(path: Path, dates: list[str], columns: dict[str, list]) -> None:
    df = pd.DataFrame(columns, index=pd.to_datetime(dates))
    df.index.name = "date"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)


@pytest.fixture
def service(tmp_path: Path) -> DailySnapshotService:
    ds = _make_service(tmp_path)
    _write_csv(ds.files["volume"], DATES, {"total_amount_yi": [6000.0, 6500.0, 6800.0]})
    _write_csv(ds.files["turnover"], DATES, {"turnover_rate": [0.90, 0.95, 1.00]})
    _write_csv(ds.files["margin"], DATES, {"margin_balance_yi": [14000.0, 14100.0, 14200.0]})
    _write_csv(ds.files["dr007"], DATES, {"dr007": [1.70, 1.66, 1.65]})
    _write_csv(
        ds.files["exchange_rates"], DATES,
        {"美元指数": [103.0, 103.2, 103.5], "美元人民币": [7.13, 7.12, 7.11]},
    )
    _write_csv(
        ds.files["ted_spread"], DATES,
        {"SOFR": [4.30, 4.31, 4.32], "美债3m": [4.20, 4.20, 4.21], "TED利差": [0.20, 0.21, 0.21]},
    )
    _write_csv(ds.files["hibor"], DATES, {"HIBOR_Overnight": [2.90, 2.98, 3.05]})
    _write_csv(
        ds.files["fund_flow"], DATES,
        {"北向成交额": [1000.0, 2000.0, 3000.0], "南向净流入": [10.0, 20.0, 30.0]},
    )
    _write_csv(
        ds.files["china_bond"], DATES,
        {"中国10y": [1.80, 1.78, 1.75], "中国10年-2年": [0.50, 0.48, 0.45]},
    )
    return DailySnapshotService(ds)


def test_explicit_date_takes_values(service: DailySnapshotService):
    snap = service.get_daily_snapshot("2026-08-27")
    assert snap["date"] == "2026-08-27"

    g = snap["groups"]
    assert set(g.keys()) == {"monetary_policy", "exchange_rate", "risk_appetite"}

    monetary = {i["key"]: i for i in g["monetary_policy"]["indicators"]}
    assert set(monetary.keys()) == {"dr001", "dr007", "cn_10y", "cn_10y_2y"}
    assert monetary["dr007"]["value"] == pytest.approx(1.65)
    assert monetary["dr007"]["prev_value"] == pytest.approx(1.66)
    assert monetary["dr007"]["data_date"] == "2026-08-27"
    assert monetary["cn_10y"]["value"] == pytest.approx(1.75)
    assert monetary["cn_10y"]["prev_value"] == pytest.approx(1.78)
    assert monetary["cn_10y"]["data_date"] == "2026-08-27"
    assert monetary["cn_10y_2y"]["value"] == pytest.approx(0.45)
    assert monetary["cn_10y_2y"]["prev_value"] == pytest.approx(0.48)
    assert monetary["cn_10y_2y"]["data_date"] == "2026-08-27"

    ex = {i["key"]: i for i in g["exchange_rate"]["indicators"]}
    assert set(ex.keys()) == {
        "dollar_index", "usd_cny", "ted_spread", "hibor_overnight",
        "north_today_yi", "north_7d_avg_yi", "north_7d_change_pct",
    }
    assert ex["dollar_index"]["value"] == pytest.approx(103.5)
    assert ex["usd_cny"]["prev_value"] == pytest.approx(7.12)
    assert ex["hibor_overnight"]["value"] == pytest.approx(3.05)
    assert ex["hibor_overnight"]["data_date"] == "2026-08-27"
    assert ex["north_today_yi"]["value"] == pytest.approx(3000.0)
    assert ex["north_today_yi"]["prev_value"] == pytest.approx(2000.0)
    assert ex["north_today_yi"]["data_date"] == "2026-08-27"
    # 仅 3 个交易日,不足 7 日窗口 → 均值/环比为 None
    assert ex["north_7d_avg_yi"]["value"] is None
    assert ex["north_7d_change_pct"]["value"] is None

    risk = {i["key"]: i for i in g["risk_appetite"]["indicators"]}
    assert set(risk.keys()) == {"volume", "turnover", "margin", "south_net_yi"}
    assert risk["volume"]["value"] == pytest.approx(6800.0)
    assert risk["south_net_yi"]["value"] == pytest.approx(30.0)
    assert risk["south_net_yi"]["prev_value"] == pytest.approx(20.0)


def test_fallback_when_date_beyond_data(service: DailySnapshotService):
    """查询晚于最新数据的日期(如 15:00 后当日未入库)→ asof 回退 + 标注实际日期"""
    snap = service.get_daily_snapshot("2026-08-28")
    ind = snap["groups"]["monetary_policy"]["indicators"][1]  # dr007 仍取自 CSV
    assert snap["date"] == "2026-08-28"
    assert ind["value"] == pytest.approx(1.65)
    assert ind["data_date"] == "2026-08-27"


def test_fallback_skips_nan(service: DailySnapshotService, tmp_path: Path):
    """所查日期该指标为 NaN(如 TED 某日缺更)→ 跳过 NaN 回退到再前一日"""
    ted_path = tmp_path / "ted_spread.csv"
    df = pd.read_csv(ted_path, index_col=0, parse_dates=True)
    df.loc["2026-08-27", "TED利差"] = float("nan")
    df.to_csv(ted_path)

    snap = service.get_daily_snapshot("2026-08-27")
    ted = {i["key"]: i for i in snap["groups"]["exchange_rate"]["indicators"]}["ted_spread"]
    assert ted["value"] == pytest.approx(0.21)  # 08-26 的值
    assert ted["data_date"] == "2026-08-26"


def test_default_date_before_close(service: DailySnapshotService):
    """15:00 前 → 今日之前最近的 volume 交易日"""
    now = datetime(2026, 8, 28, 10, 0)
    snap = service.get_daily_snapshot(now=now)
    assert snap["date"] == "2026-08-27"


def test_default_date_before_close_same_day(service: DailySnapshotService):
    """15:00 前,当日盘中 → 前一交易日(不是当日)"""
    now = datetime(2026, 8, 27, 10, 0)
    snap = service.get_daily_snapshot(now=now)
    assert snap["date"] == "2026-08-26"


def test_default_date_after_close(service: DailySnapshotService):
    """15:00 后 → 今日(即使当日数据未入库,行级回退兜底)"""
    now = datetime(2026, 8, 28, 15, 30)
    snap = service.get_daily_snapshot(now=now)
    assert snap["date"] == "2026-08-28"


def test_dates_list_desc_and_includes_today(service: DailySnapshotService):
    """dates:volume 交易日 ∪ 今日,降序"""
    now = datetime(2026, 8, 28, 16, 0)
    snap = service.get_daily_snapshot(now=now)
    dates = snap["dates"]
    assert dates == sorted(dates, reverse=True)
    assert dates[0] == "2026-08-28"  # 今日
    assert dates[1:] == ["2026-08-27", "2026-08-26", "2026-08-25"]
    assert len(dates) <= 61  # 60 个交易日 + 今日


def test_empty_volume_falls_back_to_today(tmp_path: Path):
    """volume 无数据 → dates 仅含今日,默认日期兜底今日,指标全空"""
    ds = _make_service(tmp_path)
    service = DailySnapshotService(ds)
    now = datetime(2026, 8, 28, 10, 0)
    snap = service.get_daily_snapshot(now=now)
    assert snap["date"] == "2026-08-28"
    assert snap["dates"] == ["2026-08-28"]
    # monetary_policy 组 4 个指标全应为空值(无数据)
    inds = snap["groups"]["monetary_policy"]["indicators"]
    assert len(inds) == 4
    assert {i["key"] for i in inds} == {"dr001", "dr007", "cn_10y", "cn_10y_2y"}
    assert all(i["value"] is None and i["data_date"] is None for i in inds)


def test_route_rejects_invalid_date_format():
    """路由层:非法 date 格式 → 400"""
    from src.api.routes import get_daily_snapshot as route

    with pytest.raises(HTTPException) as exc_info:
        route(date="2026/08/28")
    assert exc_info.value.status_code == 400


def test_dr001_missing_csv_does_not_affect_dr007(service: DailySnapshotService):
    """DR001 无数据(改造后读 dr001.csv,fixture 未写该文件=数据缺失) → DR001 value 为 null,DR007 仍正常返回"""
    snap = service.get_daily_snapshot("2026-08-27")

    monetary = {i["key"]: i for i in snap["groups"]["monetary_policy"]["indicators"]}
    assert monetary["dr001"]["value"] is None
    assert monetary["dr001"]["data_date"] is None
    # DR007 不受影响
    assert monetary["dr007"]["value"] == pytest.approx(1.65)
    assert monetary["dr007"]["data_date"] == "2026-08-27"


def test_china_bond_asof_fallback(service: DailySnapshotService):
    """查询晚于最新数据的日期 → 中债 2 指标 asof 回退最近可得值 + data_date 标注"""
    snap = service.get_daily_snapshot("2026-08-28")
    monetary = {i["key"]: i for i in snap["groups"]["monetary_policy"]["indicators"]}
    assert snap["date"] == "2026-08-28"
    assert monetary["cn_10y"]["value"] == pytest.approx(1.75)
    assert monetary["cn_10y"]["prev_value"] == pytest.approx(1.78)
    assert monetary["cn_10y"]["data_date"] == "2026-08-27"
    assert monetary["cn_10y_2y"]["value"] == pytest.approx(0.45)
    assert monetary["cn_10y_2y"]["data_date"] == "2026-08-27"


def test_china_bond_missing_csv_returns_null(tmp_path: Path):
    """china_bond.csv 缺失 → 中债 2 指标 value/data_date 均为 None,接口不报错"""
    ds = _make_service(tmp_path)
    service = DailySnapshotService(ds)
    snap = service.get_daily_snapshot("2026-08-27")
    monetary = {i["key"]: i for i in snap["groups"]["monetary_policy"]["indicators"]}
    assert {k for k in monetary if k.startswith("cn_")} == {"cn_10y", "cn_10y_2y"}
    assert monetary["cn_10y"]["value"] is None
    assert monetary["cn_10y"]["data_date"] is None
    assert monetary["cn_10y_2y"]["value"] is None
    assert monetary["cn_10y_2y"]["data_date"] is None


def _make_fund_flow_service(tmp_path: Path, days: int) -> DailySnapshotService:
    """构造只含 fund_flow(北向成交额=1..N,南向净流入=10*i)的服务,交易日为连续工作日"""
    ds = _make_service(tmp_path)
    dates = [d.strftime("%Y-%m-%d") for d in pd.date_range("2026-07-01", periods=days, freq="B")]
    _write_csv(
        ds.files["fund_flow"], dates,
        {
            "北向成交额": [float(i) for i in range(1, days + 1)],
            "南向净流入": [10.0 * i for i in range(1, days + 1)],
        },
    )
    return DailySnapshotService(ds)


def test_north_7d_window_with_full_data(tmp_path: Path):
    """14 个交易日:北向成交额=1..14

    查 2026-07-20(第 14 日):当日 14;当前窗口(8..14)均值 11;
    前一窗口(1..7)均值 4 → 环比 (11-4)/4×100 = 175%
    """
    service = _make_fund_flow_service(tmp_path, days=14)
    snap = service.get_daily_snapshot("2026-07-20")
    ex = {i["key"]: i for i in snap["groups"]["exchange_rate"]["indicators"]}
    assert ex["north_today_yi"]["value"] == pytest.approx(14.0)
    assert ex["north_today_yi"]["prev_value"] == pytest.approx(13.0)
    assert ex["north_7d_avg_yi"]["value"] == pytest.approx(11.0)
    assert ex["north_7d_avg_yi"]["prev_value"] is None
    assert ex["north_7d_change_pct"]["value"] == pytest.approx(175.0)
    assert ex["north_7d_change_pct"]["data_date"] == "2026-07-20"


def test_north_7d_asof_with_partial_prev_window(tmp_path: Path):
    """asof 查中间日期(2026-07-09=第 7 个工作日):当前窗口=1..7 均值 4;
    前一窗口不足 7 日 → 环比为 None 而非报错"""
    service = _make_fund_flow_service(tmp_path, days=14)
    snap = service.get_daily_snapshot("2026-07-09")
    ex = {i["key"]: i for i in snap["groups"]["exchange_rate"]["indicators"]}
    assert ex["north_today_yi"]["value"] == pytest.approx(7.0)
    assert ex["north_7d_avg_yi"]["value"] == pytest.approx(4.0)
    assert ex["north_7d_change_pct"]["value"] is None
    assert ex["north_7d_change_pct"]["data_date"] == "2026-07-09"


def test_north_window_insufficient_returns_none(tmp_path: Path):
    """仅 6 个交易日:窗口不足 → 均值/环比 value=None,data_date 仍标注最后可得日"""
    service = _make_fund_flow_service(tmp_path, days=6)
    snap = service.get_daily_snapshot("2026-07-08")
    ex = {i["key"]: i for i in snap["groups"]["exchange_rate"]["indicators"]}
    assert ex["north_today_yi"]["value"] == pytest.approx(6.0)
    assert ex["north_7d_avg_yi"]["value"] is None
    assert ex["north_7d_change_pct"]["value"] is None
    assert ex["north_7d_avg_yi"]["data_date"] == "2026-07-08"


def test_fund_flow_missing_csv_returns_null(tmp_path: Path):
    """fund_flow.csv 缺失 → 北向 3 指标 + 南向 value/data_date 均为 None,接口不报错"""
    ds = _make_service(tmp_path)
    service = DailySnapshotService(ds)
    snap = service.get_daily_snapshot("2026-08-27")
    ex = {i["key"]: i for i in snap["groups"]["exchange_rate"]["indicators"]}
    assert {k for k in ex if k.startswith("north_")} == {
        "north_today_yi", "north_7d_avg_yi", "north_7d_change_pct",
    }
    for k in ("north_today_yi", "north_7d_avg_yi", "north_7d_change_pct"):
        assert ex[k]["value"] is None
        assert ex[k]["data_date"] is None
    south = {i["key"]: i for i in snap["groups"]["risk_appetite"]["indicators"]}["south_net_yi"]
    assert south["value"] is None
    assert south["data_date"] is None

"""按 Tab 查询数据接口测试"""
import os
from pathlib import Path

os.environ.setdefault("FRED_API_KEY", "test-not-a-real-key")

import pandas as pd
import pytest

from src.services import data_service as ds_mod
from src.services.data_service import DataService, VALID_DATA_TABS


def _make_service(tmp_path: Path) -> DataService:
    """指向 tmp_path 的 DataService，并清空 query 缓存以免污染生产 CSV 结果。"""
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


@pytest.mark.parametrize("tab", sorted(t for t in VALID_DATA_TABS if t != "comparison"))
def test_query_data_by_tab_returns_dates(tab: str):
    service = DataService()
    data = service.query_data_by_tab(tab, start_date="2024-01-01", end_date="2024-06-01")
    assert "dates" in data
    assert isinstance(data["dates"], list)


def test_query_data_by_tab_treasury_exchange_fields():
    service = DataService()
    data = service.query_data_by_tab(
        "treasury-exchange", start_date="2024-01-01", end_date="2024-06-01"
    )
    assert set(data.keys()) <= {"dates", "us_treasuries", "exchange_rates", "china_bond"}
    assert "commodities" not in data
    assert "indices" not in data


def test_query_data_by_tab_market_sentiment_fields():
    service = DataService()
    data = service.query_data_by_tab(
        "market-sentiment", start_date="2024-01-01", end_date="2024-06-01"
    )
    # fund_flow 2026-08 起并入市场情绪 Tab（北向成交额+南向三列）
    assert set(data.keys()) <= {"dates", "volume", "turnover", "margin", "fund_flow"}
    assert "us_treasuries" not in data


def test_query_data_by_tab_invalid_tab():
    service = DataService()
    with pytest.raises(ValueError, match="无效的 tab"):
        service.query_data_by_tab("macro-signal")


def test_query_data_by_tab_bonds_removed():
    """德债日债 Tab 已下线，按 Tab API 不再接受 bonds"""
    service = DataService()
    with pytest.raises(ValueError, match="无效的 tab"):
        service.query_data_by_tab("bonds")


def test_query_data_by_tab_comparison_requires_indicators():
    """服务层禁止 comparison 全量；HTTP 走 query_data_by_indicators"""
    service = DataService()
    with pytest.raises(ValueError, match="query_data_by_indicators"):
        service.query_data_by_tab("comparison")


def test_market_sentiment_dates_are_union_not_us_treasuries(tmp_path):
    """market-sentiment 的 dates 是 volume/turnover/margin 有值日期并集，且不含 us_treasuries。"""
    service = _make_service(tmp_path)
    _write_csv(
        tmp_path / "volume.csv",
        ["2026-08-26", "2026-08-27"],
        {"total_amount_yi": [1000.0, 1100.0]},
    )
    _write_csv(
        tmp_path / "turnover.csv",
        ["2026-08-26", "2026-08-27"],
        {"turnover_rate": [0.51, 0.62]},
    )
    _write_csv(
        tmp_path / "margin.csv",
        ["2026-08-27"],
        {"margin_balance_yi": [18000.0]},
    )
    us_dates = pd.bdate_range("2026-01-01", "2026-06-30").strftime("%Y-%m-%d").tolist()
    _write_csv(
        tmp_path / "us_treasuries.csv",
        us_dates,
        {
            "美债3m": [4.0] * len(us_dates),
            "美债2y": [4.1] * len(us_dates),
            "美债10y": [4.2] * len(us_dates),
        },
    )

    data = service.query_data_by_tab(
        "market-sentiment", start_date="2026-01-01", end_date="2026-08-31"
    )

    assert "us_treasuries" not in data
    assert set(data["dates"]) == {"2026-08-26", "2026-08-27"}
    assert data["dates"] == sorted(data["dates"])


def test_rates_result_includes_us_treasuries(tmp_path):
    """利率 Tab 响应必须含 us_treasuries（RatesChart 读 3m）。"""
    service = _make_service(tmp_path)
    _write_csv(
        tmp_path / "us_treasuries.csv",
        ["2026-08-26", "2026-08-27"],
        {"美债3m": [4.2, 4.3], "美债2y": [3.8, 3.9], "美债10y": [4.0, 4.1]},
    )
    _write_csv(
        tmp_path / "ted_spread.csv",
        ["2026-08-26", "2026-08-27"],
        {"SOFR": [5.3, 5.31], "美债3m": [4.2, 4.3], "TED利差": [1.1, 1.01]},
    )
    _write_csv(
        tmp_path / "china_bond.csv",
        ["2026-08-26", "2026-08-27"],
        {"中国国债收益率10年": [1.8, 1.81], "中国10年-2年": [0.4, 0.41]},
    )
    _write_csv(
        tmp_path / "dr007.csv",
        ["2026-08-26", "2026-08-27"],
        {"dr007": [1.5, 1.51]},
    )

    data = service.query_data_by_tab("rates", start_date="2026-08-01", end_date="2026-08-31")

    assert "us_treasuries" in data
    assert "3m" in data["us_treasuries"]
    assert len(data["us_treasuries"]["3m"]) == len(data["dates"])
    assert "ted_spread" in data
    assert "china_bond" in data
    assert "dr007" in data


def test_market_sentiment_two_volume_days_dates_length_is_two(tmp_path):
    """只有 2 个成交额交易日时，dates 长度为 2，不是美债日历或自然日填充。"""
    service = _make_service(tmp_path)
    _write_csv(
        tmp_path / "volume.csv",
        ["2026-08-26", "2026-08-27"],
        {"total_amount_yi": [1000.0, 1100.0]},
    )
    us_dates = pd.bdate_range("2026-01-01", "2026-06-30").strftime("%Y-%m-%d").tolist()
    _write_csv(
        tmp_path / "us_treasuries.csv",
        us_dates,
        {
            "美债3m": [4.0] * len(us_dates),
            "美债2y": [4.1] * len(us_dates),
            "美债10y": [4.2] * len(us_dates),
        },
    )

    data = service.query_data_by_tab(
        "market-sentiment", start_date="2026-01-01", end_date="2026-08-31"
    )

    assert len(data["dates"]) == 2
    assert data["dates"] == ["2026-08-26", "2026-08-27"]
    assert len(data["volume"]) == 2


def test_query_data_by_indicators_default_four_ids(tmp_path):
    """默认四指标只拉 exchange_rates / us_treasuries / vix / commodities，不含 indices。"""
    service = _make_service(tmp_path)
    dates = ["2026-08-26", "2026-08-27"]
    _write_csv(
        tmp_path / "exchange_rates.csv",
        dates,
        {
            "美元指数": [100.0, 101.0],
            "美元人民币": [7.1, 7.11],
            "美元日元": [148.0, 149.0],
            "美元欧元": [0.92, 0.93],
        },
    )
    _write_csv(
        tmp_path / "us_treasuries.csv",
        dates,
        {"美债3m": [4.2, 4.3], "美债2y": [3.8, 3.9], "美债10y": [4.0, 4.1]},
    )
    _write_csv(tmp_path / "vix.csv", dates, {"Close_VIX": [15.0, 16.0]})
    _write_csv(
        tmp_path / "commodities.csv",
        dates,
        {"黄金": [500.0, 501.0], "白银": [6.0, 6.1], "原油": [80.0, 81.0], "铜": [9000.0, 9100.0]},
    )
    _write_csv(
        tmp_path / "indices.csv",
        dates,
        {"HKHSI": [17000.0, 17100.0], "SH000001": [3000.0, 3010.0],
         "SPX": [5000.0, 5010.0], "IXIC": [16000.0, 16100.0], "DJI": [39000.0, 39100.0]},
    )

    data = service.query_data_by_indicators(
        ["dxy", "us_10y", "vix", "gold"],
        start_date="2026-08-01",
        end_date="2026-08-31",
    )

    assert "exchange_rates" in data
    assert "us_treasuries" in data
    assert "vix" in data
    assert "commodities" in data
    assert "indices" not in data
    assert "dates" in data


def test_query_data_by_indicators_unknown_id_raises(tmp_path):
    service = _make_service(tmp_path)
    with pytest.raises(ValueError, match="未知"):
        service.query_data_by_indicators(["dxy", "not_a_real_id"])


def test_query_data_by_indicators_empty_list_raises(tmp_path):
    service = _make_service(tmp_path)
    with pytest.raises(ValueError):
        service.query_data_by_indicators([])


def test_get_data_comparison_without_indicators_is_400():
    from fastapi import HTTPException
    from src.api.routes import get_data_by_tab

    with pytest.raises(HTTPException) as exc:
        get_data_by_tab(tab="comparison", indicators=None)
    assert exc.value.status_code == 400
    assert "indicators" in str(exc.value.detail).lower()


def test_get_data_other_tab_with_indicators_is_400():
    from fastapi import HTTPException
    from src.api.routes import get_data_by_tab

    with pytest.raises(HTTPException) as exc:
        get_data_by_tab(tab="rates", indicators="dxy,vix")
    assert exc.value.status_code == 400


def test_get_data_macro_signal_tab_is_400():
    from fastapi import HTTPException
    from src.api.routes import get_data_by_tab

    with pytest.raises(HTTPException) as exc:
        get_data_by_tab(tab="macro-signal")
    assert exc.value.status_code == 400


def test_get_data_bonds_tab_is_400():
    from fastapi import HTTPException
    from src.api.routes import get_data_by_tab

    with pytest.raises(HTTPException) as exc:
        get_data_by_tab(tab="bonds")
    assert exc.value.status_code == 400

"""按 Tab 查询数据接口测试"""
import pytest
from src.services.data_service import DataService, VALID_DATA_TABS


@pytest.mark.parametrize("tab", sorted(VALID_DATA_TABS))
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


def test_query_data_by_tab_bonds_fields():
    service = DataService()
    data = service.query_data_by_tab("bonds", start_date="2024-01-01", end_date="2024-06-01")
    assert set(data.keys()) <= {"dates", "eu_treasuries", "jp_treasuries"}
    assert "us_treasuries" not in data
    assert "exchange_rates" not in data


def test_query_data_by_tab_invalid_tab():
    service = DataService()
    with pytest.raises(ValueError, match="无效的 tab"):
        service.query_data_by_tab("macro-signal")

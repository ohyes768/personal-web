from unittest.mock import Mock
import asyncio
import pandas as pd
from src.api import routes


def test_old_schema_requires_refresh_but_real_gaps_do_not_loop(monkeypatch):
    fi = Mock()
    fi.check_exists.return_value = True
    fi.get_quarter.return_value = '2026Q2'
    fi.read_csv.return_value = pd.DataFrame([{'股票代码': '000090', '数据日期': '2026-06-30'}])
    reader = Mock()
    reader.read_csv.return_value = pd.DataFrame([{'股票代码': '000090'}])
    filterer = Mock()
    filterer.filter_by_3y_dividend.side_effect = lambda frame, **kwargs: frame
    monkeypatch.setattr(routes, 'financial_reader', fi)
    monkeypatch.setattr(routes, 'data_reader', reader)
    monkeypatch.setattr(routes, 'filter_service', filterer)
    monkeypatch.setattr(routes, 'find_latest_aux_file', lambda *args: 'financial.csv')
    monkeypatch.setattr(routes, 'file_mtime_iso', lambda *args: '2026-10-09')
    monkeypatch.setattr(routes, 'days_since_update', lambda *args: 0)
    result = asyncio.run(routes.get_financial_status())
    assert result['needs_update'] is True
    assert set(result['missing_schema_columns']) == routes.SCREENING_FINANCIAL_COLUMNS
    for column in routes.SCREENING_FINANCIAL_COLUMNS:
        fi.read_csv.return_value[column] = None
    result = asyncio.run(routes.get_financial_status())
    assert result['needs_update'] is False
    assert result['missing_schema_columns'] == []

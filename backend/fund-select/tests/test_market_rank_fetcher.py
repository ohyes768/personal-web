"""
rankhandler fetcher 单测（mock HTTP，不联网）
"""
from datetime import date
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from src.data.market_rank_fetcher import (
    fetch_market_rank_page,
    fetch_market_rank_bulk,
)


MOCK_RESPONSE = (
    'var rankData = {datas:['
    '"006502,财通集成电路产业股票A,CTJCDLCYGPA,2026-09-07,7.2634,7.2634,'
    '7.96,-0.99,-3.06,-6.99,78.34,121.2,478.57,391.23,83.62,626.34,'
    '2018-11-29,1,375.8517,1.50%,0.15%,1,0.15%,1,237.69"'
    '],allRecords:1,allPages:1,pageIndex:1,pageNum:50};'
)


class TestFetchMarketRankPage:
    def test_parses_jsonp_response(self):
        with patch("src.data.market_rank_fetcher.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=MOCK_RESPONSE, raise_for_status=lambda: None)
            rows = fetch_market_rank_page("gp", "2023-09-01", "2026-09-08", pi=1, pn=50)
        assert len(rows) == 1
        r = rows[0]
        assert r["code"] == "006502"
        assert r["name"] == "财通集成电路产业股票A"
        assert r["nav_latest"] == 7.2634
        assert r["ret_1w"] == -0.99
        assert r["ret_1m"] == -3.06
        assert r["ret_3y"] == 391.23
        assert r["ret_ytd"] == 83.62
        assert r["size_yi"] == 375.8517
        assert r["nav_date"] == date(2026, 9, 7)

    def test_handles_network_error(self):
        with patch("src.data.market_rank_fetcher.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text="not rankhandler", raise_for_status=lambda: None)
            with pytest.raises(ValueError, match="格式异常"):
                fetch_market_rank_page("gp", "2023-09-01", "2026-09-08")

    def test_skips_short_rows(self):
        short_response = 'var rankData = {datas:["006502,X,CTJCDLCYGPA"],allRecords:1,allPages:1};'
        with patch("src.data.market_rank_fetcher.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=short_response, raise_for_status=lambda: None)
            rows = fetch_market_rank_page("gp", "2023-09-01", "2026-09-08")
        assert rows == []


class TestFetchMarketRankBulk:
    def test_pages_through_ft(self):
        """pages_per_ft=2 调用 2 次 page，每页 1 行 → 共 2 行（不同 code）"""
        call_count = [0]

        def fake_page(ft, sd, ed, pi=1, pn=50, sc="3nzf", st="desc"):
            call_count[0] += 1
            return [{
                "code": f"00000{call_count[0]}", "name": "X", "ret_1y": 1.0,
                "nav_date": date(2026, 9, 7), "nav_latest": 1.0,
                "ret_1w": 0.5, "ret_1m": 1.0, "ret_3m": 3.0,
                "ret_6m": 6.0, "ret_2y": 10.0, "ret_3y": 15.0,
                "ret_ytd": 5.0, "ret_all": 20.0, "size_yi": 5.0,
                "ft_code": "1",
            }]

        with patch("src.data.market_rank_fetcher.fetch_market_rank_page", side_effect=fake_page):
            df = fetch_market_rank_bulk(["gp"], pages_per_ft=2, page_delay_s=0)
        assert len(df) == 2
        assert call_count[0] == 2

    def test_empty_when_fts_empty(self):
        df = fetch_market_rank_bulk([], pages_per_ft=5, page_delay_s=0)
        assert df.empty
        assert "code" in df.columns

    def test_dedup_by_code(self):
        with patch("src.data.market_rank_fetcher.fetch_market_rank_page") as mock_page:
            mock_page.return_value = [
                {"code": "000001", "name": "X", "ret_1y": 1.0,
                 "nav_date": date(2026, 9, 7), "nav_latest": 1.0,
                 "ret_1w": 0.5, "ret_1m": 1.0, "ret_3m": 3.0,
                 "ret_6m": 6.0, "ret_2y": 10.0, "ret_3y": 15.0,
                 "ret_ytd": 5.0, "ret_all": 20.0, "size_yi": 5.0,
                 "ft_code": "1"},
            ]
            df = fetch_market_rank_bulk(["gp"], pages_per_ft=3, page_delay_s=0)
        # 3 pages × 1 row each = 3 rows but all same code → dedup to 1
        assert len(df) == 1

"""baostock_service 单元测试

数据源：baostock.query_history_k_data_plus(sh.000001 / sz.399106)
一次 login 会话拉两指数日线（date, close, volume, amount, turn），
inner-join 对齐交易日后合成：
  - 两市成交额 = (sh.amount + sz.amount) / 1e8 （元 → 亿元）
  - 两市换手率 = (sh_amt*sh_turn + sz_amt*sz_turn) / (sh_amt + sz_amt)（%）

全部 mock baostock 模块，不真连。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import baostock as bs
import pandas as pd
import pytest

from src.services.baostock_service import BaostockService, get_baostock_service
from src.services.data_service import DataService

# rs.fields 顺序：date, close, volume, amount, turn
FIELDS = ["date", "close", "volume", "amount", "turn"]

SH_CODE = "sh.000001"
SZ_CODE = "sz.399106"


class FakeRS:
    """baostock ResultData 替身：error_code/error_msg/next()/get_row_data()/fields"""

    def __init__(
        self,
        rows: list[list[str]],
        fields: Optional[list[str]] = None,
        error_code: str = "0",
        error_msg: str = "success",
    ):
        self._rows = list(rows)
        self._idx = -1
        self.fields = fields if fields is not None else FIELDS
        self.error_code = error_code
        self.error_msg = error_msg

    def next(self) -> bool:
        if self._idx + 1 < len(self._rows):
            self._idx += 1
            return True
        return False

    def get_row_data(self) -> list[str]:
        return self._rows[self._idx]


class FakeLoginRS:
    """baostock login/logout 返回对象替身"""

    def __init__(self, error_code: str = "0", error_msg: str = "success"):
        self.error_code = error_code
        self.error_msg = error_msg


def install_baostock_mock(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, list[list[str]]],
    *,
    login_error: str = "0",
    query_error_code: str = "0",
    calls: Optional[list[dict[str, Any]]] = None,
    logout_calls: Optional[list[int]] = None,
) -> None:
    """把 bs.login/logout/query_history_k_data_plus 替换成 fake。

    responses: {code: [[date, close, volume, amount, turn], ...]}
    """

    def _fake_login() -> FakeLoginRS:
        return FakeLoginRS(error_code=login_error, error_msg="login failed" if login_error != "0" else "success")

    def _fake_logout() -> FakeLoginRS:
        if logout_calls is not None:
            logout_calls.append(1)
        return FakeLoginRS()

    def _fake_query(code, fields, start_date=None, end_date=None, frequency="d", adjustflag="3"):
        if calls is not None:
            calls.append({"code": code, "start": start_date, "end": end_date})
        return FakeRS(
            responses.get(code, []),
            fields=FIELDS,
            error_code=query_error_code,
            error_msg="query failed" if query_error_code != "0" else "success",
        )

    monkeypatch.setattr(bs, "login", _fake_login)
    monkeypatch.setattr(bs, "logout", _fake_logout)
    monkeypatch.setattr(bs, "query_history_k_data_plus", _fake_query)


# 两天标准 fixture（手算验证用）
# day1: sh amount=1e12 turn=1.0 / sz amount=5e11 turn=2.0
#   volume = 1.5e12 / 1e8 = 15000 亿
#   turnover = (1e12*1 + 5e11*2) / 1.5e12 = 2e12/1.5e12 = 1.3333
# day2: sh amount=2e12 turn=0.5 / sz amount=1e12 turn=1.5
#   volume = 3e12 / 1e8 = 30000 亿
#   turnover = (2e12*0.5 + 1e12*1.5) / 3e12 = 2.5e12/3e12 = 0.8333
SH_ROWS_2D = [
    ["2026-08-27", "3200.00", "1e11", "1e12", "1.0"],
    ["2026-08-28", "3210.00", "1.2e11", "2e12", "0.5"],
]
SZ_ROWS_2D = [
    ["2026-08-27", "2000.00", "5e10", "5e11", "2.0"],
    ["2026-08-28", "2010.00", "6e10", "1e12", "1.5"],
]


# ============================================================
# 用例 1：两指数合成（amount 求和/1e8、turn 成交额加权）
# ============================================================

@pytest.mark.unit
def test_fetch_history_combines_amount_and_weighted_turnover(monkeypatch):
    """两市成交额 = 沪+深 amount/1e8；换手率 = 成交额加权（手算 fixture）"""
    install_baostock_mock(monkeypatch, {SH_CODE: SH_ROWS_2D, SZ_CODE: SZ_ROWS_2D})

    service = BaostockService()
    result = service.fetch_history("2026-08-01", "2026-08-31")

    assert result["status"] == "ok"
    volume = result["volume"]
    turnover = result["turnover"]

    assert volume["date"].tolist() == ["2026-08-27", "2026-08-28"]
    assert volume["total_amount_yi"].iloc[0] == pytest.approx(15000.0)
    assert volume["total_amount_yi"].iloc[1] == pytest.approx(30000.0)

    assert turnover["date"].tolist() == ["2026-08-27", "2026-08-28"]
    assert turnover["turnover_rate"].iloc[0] == pytest.approx(1.3333, rel=1e-3)
    assert turnover["turnover_rate"].iloc[1] == pytest.approx(0.8333, rel=1e-3)


@pytest.mark.unit
def test_get_baostock_service_is_singleton():
    """模块级单例：两次获取同一实例"""
    assert get_baostock_service() is get_baostock_service()


# ============================================================
# 用例 2：交易日对齐（inner-join 剔除单边缺失日）
# ============================================================

@pytest.mark.unit
def test_fetch_history_inner_joins_on_date(monkeypatch):
    """某日仅一指数有值 → 该日被剔除（inner-join on date）"""
    sh_rows = [
        ["2026-08-26", "3190.00", "9e10", "9e11", "0.9"],
        ["2026-08-27", "3200.00", "1e11", "1e12", "1.0"],
        ["2026-08-28", "3210.00", "1.2e11", "2e12", "0.5"],
    ]
    sz_rows = [
        ["2026-08-26", "1990.00", "4e10", "4e11", "1.8"],
        ["2026-08-28", "2010.00", "6e10", "1e12", "1.5"],
    ]
    install_baostock_mock(monkeypatch, {SH_CODE: sh_rows, SZ_CODE: sz_rows})

    result = BaostockService().fetch_history("2026-08-01", "2026-08-31")

    assert result["status"] == "ok"
    # 08-27 深市缺 → 剔除；无重复日期
    assert result["volume"]["date"].tolist() == ["2026-08-26", "2026-08-28"]
    assert result["turnover"]["date"].tolist() == ["2026-08-26", "2026-08-28"]


# ============================================================
# 用例 3：空串/异常值 → NaN 行被 dropna
# ============================================================

@pytest.mark.unit
def test_fetch_history_drops_nan_rows_per_indicator(monkeypatch):
    """空串/非法数字 → NaN；volume 与 turnover 分别 dropna（行数可不同）

    day2 sh amount=""  → volume/turnover 都剔除
    day3 sz turn="abc" → 仅 turnover 剔除，volume 保留
    """
    sh_rows = [
        ["2026-08-26", "3190.00", "9e10", "9e11", "0.9"],
        ["2026-08-27", "3200.00", "1e11", "", "1.0"],       # amount 空串
        ["2026-08-28", "3210.00", "1.2e11", "2e12", "0.5"],
    ]
    sz_rows = [
        ["2026-08-26", "1990.00", "4e10", "4e11", "1.8"],
        ["2026-08-27", "2000.00", "5e10", "5e11", "2.0"],
        ["2026-08-28", "2010.00", "6e10", "1e12", "abc"],   # turn 非法
    ]
    install_baostock_mock(monkeypatch, {SH_CODE: sh_rows, SZ_CODE: sz_rows})

    result = BaostockService().fetch_history("2026-08-01", "2026-08-31")

    assert result["status"] == "ok"
    volume = result["volume"]
    turnover = result["turnover"]
    assert not volume["total_amount_yi"].isna().any()
    assert not turnover["turnover_rate"].isna().any()
    # day2 沪 amount NaN → 两指标都剔除；day3 深 turn NaN → 仅 turnover 剔除
    assert volume["date"].tolist() == ["2026-08-26", "2026-08-28"]
    assert turnover["date"].tolist() == ["2026-08-26"]


# ============================================================
# 用例 4：login 失败 / error_code != 0 → status=failed 不抛异常
# ============================================================

@pytest.mark.unit
def test_fetch_history_login_failure_returns_failed(monkeypatch):
    """login 失败 → status=failed，不抛异常"""
    install_baostock_mock(
        monkeypatch,
        {SH_CODE: SH_ROWS_2D, SZ_CODE: SZ_ROWS_2D},
        login_error="1",
    )

    result = BaostockService().fetch_history("2026-08-01", "2026-08-31")

    assert result["status"] == "failed"
    assert result["volume"].empty
    assert result["turnover"].empty
    assert "login" in result.get("error", "")


@pytest.mark.unit
def test_fetch_history_query_error_returns_failed(monkeypatch):
    """query_history_k_data_plus error_code != 0 → status=failed，不抛异常"""
    logout_calls: list[int] = []
    install_baostock_mock(
        monkeypatch,
        {SH_CODE: SH_ROWS_2D, SZ_CODE: SZ_ROWS_2D},
        query_error_code="10001",
        logout_calls=logout_calls,
    )

    result = BaostockService().fetch_history("2026-08-01", "2026-08-31")

    assert result["status"] == "failed"
    assert "query failed" in result.get("error", "")
    # query 抛错也必须 logout（finally）
    assert len(logout_calls) == 1


# ============================================================
# fetch_today：近 10 日窗口 + 最新单点
# ============================================================

@pytest.mark.unit
def test_fetch_today_returns_latest_point_and_window(monkeypatch):
    """fetch_today 拉近 10 个自然日窗口，返回最新交易日单点 + 小批量"""
    calls: list[dict[str, Any]] = []
    sh_rows = [
        ["2026-08-26", "3190.00", "9e10", "9e11", "0.9"],
        ["2026-08-27", "3200.00", "1e11", "1e12", "1.0"],
        ["2026-08-28", "3210.00", "1.2e11", "2e12", "0.5"],
    ]
    sz_rows = [
        ["2026-08-26", "1990.00", "4e10", "4e11", "1.8"],
        ["2026-08-27", "2000.00", "5e10", "5e11", "2.0"],
        ["2026-08-28", "2010.00", "6e10", "1e12", "1.5"],
    ]
    install_baostock_mock(
        monkeypatch,
        {SH_CODE: sh_rows, SZ_CODE: sz_rows},
        calls=calls,
    )

    result = BaostockService().fetch_today(now=datetime(2026, 8, 28, 17, 0))

    assert result["status"] == "ok"
    # 单点取序列末行
    assert result["date"] == "2026-08-28"
    assert result["total_amount_yi"] == pytest.approx(30000.0)
    assert result["turnover_rate"] == pytest.approx(0.8333, rel=1e-3)
    # 小批量落库用 DataFrame
    assert len(result["volume"]) == 3
    assert len(result["turnover"]) == 3

    # 查询窗口 = 今天往前 10 个自然日
    assert calls[0]["start"] == "2026-08-18"
    assert calls[0]["end"] == "2026-08-28"
    assert calls[1]["start"] == "2026-08-18"
    assert calls[1]["end"] == "2026-08-28"


@pytest.mark.unit
def test_fetch_today_propagates_failure(monkeypatch):
    """底层 fetch_history 失败 → fetch_today 同样 failed、无数据"""
    install_baostock_mock(
        monkeypatch,
        {SH_CODE: SH_ROWS_2D, SZ_CODE: SZ_ROWS_2D},
        login_error="1",
    )

    result = BaostockService().fetch_today(now=datetime(2026, 8, 28, 17, 0))

    assert result["status"] == "failed"
    assert result["date"] is None
    assert result["total_amount_yi"] is None
    assert result["turnover_rate"] is None
    assert result["volume"].empty


# ============================================================
# 用例 5：回补幂等（同数据重复 save 无重复行，keep=last）
# ============================================================

@pytest.mark.integration
def test_save_volume_idempotent_on_baostock_shape(tmp_path):
    """baostock 输出形状重复写 volume.csv 无重复行（回补端点幂等的落库保证）"""
    csv_path = tmp_path / "volume.csv"
    service = DataService()

    df = pd.DataFrame({
        "date": ["2026-08-27", "2026-08-28"],
        "total_amount_yi": [15000.0, 30000.0],
    })
    service.save_volume_data(df, path=csv_path)
    service.save_volume_data(df, path=csv_path)

    loaded = service.load_volume(path=csv_path)
    assert len(loaded) == 2
    assert loaded.index.duplicated().sum() == 0


@pytest.mark.integration
def test_save_turnover_idempotent_on_baostock_shape(tmp_path):
    """baostock 输出形状重复写 turnover.csv 无重复行"""
    csv_path = tmp_path / "turnover.csv"
    service = DataService()

    df = pd.DataFrame({
        "date": ["2026-08-27", "2026-08-28"],
        "turnover_rate": [1.3333, 0.8333],
    })
    service.save_turnover_data(df, path=csv_path)
    service.save_turnover_data(df, path=csv_path)

    loaded = service.load_turnover(path=csv_path)
    assert len(loaded) == 2
    assert loaded.index.duplicated().sum() == 0

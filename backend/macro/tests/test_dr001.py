"""DR001 fetcher 单元测试

数据源：中国货币网 prr-chrt.csv（与 DR007 同一文件）
列含义（index，实测 2026-09-15 共 9 列）：
  0 日期（YYYY-MM-DD）
  1-5 其他盘口字段（本服务不使用）
  6 DR001 加权利率(%)  ← DR001 取这一列
  7 DR007 加权利率(%)
  8 DR014 加权利率(%)
"""
import asyncio
from unittest.mock import patch

import pandas as pd
import pytest

from src.services.dr001_service import DR001Service
from src.services.data_service import DataService


@pytest.mark.unit
def test_parse_csv_extracts_dr001_column():
    """解析：index 6 为当日 DR001 利率（%）——真实 9 列格式样本"""
    csv_text = (
        "2026-09-15,,,,,,1.4266,1.4244,1.4169\n"
        "2026-09-14,,,,,,1.4200,1.4100,1.4000\n"
    )
    df = DR001Service.parse_csv(csv_text)

    assert list(df.columns) == ["date", "dr001"]
    assert len(df) == 2
    # parse_csv 按日期升序输出，所以 iloc[0] 是较早的 9/14，iloc[-1] 是最新 9/15
    assert df.iloc[0]["date"] == pd.Timestamp("2026-09-14")
    assert df.iloc[0]["dr001"] == pytest.approx(1.4200)
    assert df.iloc[-1]["date"] == pd.Timestamp("2026-09-15")
    assert df.iloc[-1]["dr001"] == pytest.approx(1.4266)


@pytest.mark.unit
def test_parse_csv_skips_rows_with_fewer_than_9_cols():
    """解析：列数不足 9 列（含老格式 8 列行）→ 跳过，不猜测列位"""
    csv_text = (
        "2026-08-20,1.6200,1.6200,1234,500,1.7,1.6,1.6200\n"    # 老格式 8 列
        "2026-08-22,1.6500,1.6500\n"                            # 短行
        "2026-08-21,,,,,,1.6300,1.6300,1.6100\n"                # 合法 9 列
    )
    df = DR001Service.parse_csv(csv_text)

    assert len(df) == 1
    assert df.iloc[0]["date"] == pd.Timestamp("2026-08-21")
    assert df.iloc[0]["dr001"] == pytest.approx(1.6300)


@pytest.mark.unit
def test_parse_csv_skips_non_numeric_value():
    """解析：index 6 非 float → 跳过该行"""
    csv_text = (
        "2026-09-14,,,,,,notnum,1.4244,1.4169\n"
        "2026-09-15,,,,,,1.4266,1.4244,1.4169\n"
    )
    df = DR001Service.parse_csv(csv_text)

    assert len(df) == 1
    assert df.iloc[0]["date"] == pd.Timestamp("2026-09-15")


@pytest.mark.unit
def test_parse_csv_empty_input_returns_empty_df():
    """空输入 → 空 DataFrame（列结构不变）"""
    df = DR001Service.parse_csv("")
    assert list(df.columns) == ["date", "dr001"]
    assert len(df) == 0


@pytest.mark.unit
def test_parse_csv_sorts_by_date_ascending():
    """解析：CSV 倒序时按日期升序返回"""
    csv_text = (
        "2026-09-15,,,,,,1.4266,1.4244,1.4169\n"
        "2026-09-11,,,,,,1.4000,1.4000,1.3900\n"
        "2026-09-14,,,,,,1.4200,1.4100,1.4000\n"
    )
    df = DR001Service.parse_csv(csv_text)

    assert df["date"].tolist() == [
        pd.Timestamp("2026-09-11"),
        pd.Timestamp("2026-09-14"),
        pd.Timestamp("2026-09-15"),
    ]


@pytest.mark.unit
def test_parse_csv_deduplicates_by_date():
    """解析：同日期多行 → 去重保留首次出现的值"""
    csv_text = (
        "2026-09-15,,,,,,1.4266,1.4244,1.4169\n"
        "2026-09-15,,,,,,1.9999,1.4244,1.4169\n"
    )
    df = DR001Service.parse_csv(csv_text)

    assert len(df) == 1
    assert df.iloc[0]["dr001"] == pytest.approx(1.4266)


@pytest.mark.unit
def test_fetch_history_filters_by_date_range():
    """fetch_history：拉全量 CSV 后筛 [start, end] 区间（mock 网络层）"""
    csv_text = (
        "2026-09-10,,,,,,1.3900,1.3900,1.3800\n"
        "2026-09-11,,,,,,1.4000,1.4000,1.3900\n"
        "2026-09-14,,,,,,1.4200,1.4100,1.4000\n"
        "2026-09-15,,,,,,1.4266,1.4244,1.4169\n"
    )
    service = DR001Service()

    with patch.object(service, "fetch_csv_text", return_value=csv_text):
        df = asyncio.run(
            service.fetch_history(pd.Timestamp("2026-09-11"), pd.Timestamp("2026-09-14"))
        )

    assert df["date"].tolist() == [
        pd.Timestamp("2026-09-11"),
        pd.Timestamp("2026-09-14"),
    ]
    assert df["dr001"].tolist() == [pytest.approx(1.4000), pytest.approx(1.4200)]


@pytest.mark.unit
def test_fetch_latest_returns_empty_when_no_new_data():
    """fetch_latest：区间内无新数据（如节假日）→ 空 DataFrame"""
    csv_text = "2026-09-15,,,,,,1.4266,1.4244,1.4169\n"
    service = DR001Service()

    with patch.object(service, "fetch_csv_text", return_value=csv_text):
        df = asyncio.run(
            service.fetch_latest(pd.Timestamp("2026-09-16"), pd.Timestamp("2026-09-17"))
        )

    assert df.empty


@pytest.mark.integration
def test_save_and_load_dr001_roundtrip(tmp_path):
    """save_dr001_data → load_dr001 能读回（首次写入）"""
    csv_path = tmp_path / "dr001.csv"
    df_to_write = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-13", "2026-09-14", "2026-09-15"]),
        "dr001": [1.40, 1.42, 1.4266],
    })

    service = DataService()
    service.save_dr001_data(df_to_write, path=csv_path)
    assert csv_path.exists()

    loaded = service.load_dr001(path=csv_path)
    assert len(loaded) == 3
    assert loaded["dr001"].iloc[-1] == pytest.approx(1.4266)
    assert loaded["dr001"].iloc[0] == pytest.approx(1.40)


@pytest.mark.integration
def test_save_dr001_merges_with_existing_data(tmp_path):
    """save_dr001_data 与现有 CSV 合并（按 date 去重，新值覆盖旧值）"""
    csv_path = tmp_path / "dr001.csv"
    service = DataService()

    # 第一次写入
    first = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-13", "2026-09-14"]),
        "dr001": [1.40, 1.42],
    })
    service.save_dr001_data(first, path=csv_path)

    # 第二次写入：含 1 条旧日期（覆盖）+ 1 条新日期
    second = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-14", "2026-09-15"]),
        "dr001": [1.99, 1.4266],  # 9/14 应覆盖为 1.99
    })
    service.save_dr001_data(second, path=csv_path)

    loaded = service.load_dr001(path=csv_path)
    assert len(loaded) == 3
    # 验证合并：9/14 被新值覆盖
    assert loaded.loc[pd.Timestamp("2026-09-14"), "dr001"] == pytest.approx(1.99)
    assert loaded.loc[pd.Timestamp("2026-09-15"), "dr001"] == pytest.approx(1.4266)


@pytest.mark.integration
def test_save_dr001_creates_file_with_header(tmp_path):
    """save_dr001_data 写入空 df 也能建带 header 的空文件"""
    csv_path = tmp_path / "dr001.csv"
    empty_df = pd.DataFrame(columns=["date", "dr001"])

    service = DataService()
    service.save_dr001_data(empty_df, path=csv_path)
    assert csv_path.exists()

    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert "date" in header
    assert "dr001" in header


@pytest.mark.integration
def test_load_dr001_missing_file_returns_empty(tmp_path):
    """dr001.csv 不存在 → 空 DataFrame（与 load_dr007 行为一致）"""
    service = DataService()
    loaded = service.load_dr001(path=tmp_path / "not-exist.csv")
    assert loaded.empty

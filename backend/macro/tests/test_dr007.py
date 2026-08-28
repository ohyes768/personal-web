"""DR007 fetcher 单元测试

数据源：中国货币网 prr-chrt.csv
列含义（index）：
  0 日期（YYYY-MM-DD）
  1 加权利率(%)
  2 加权平均(%)
  3 成交笔数
  4 成交量(亿)
  5 卖开利率
  6 买开利率
  7 加权平均(%)  ← DR007 取这一列（与 monetary-policy-skill 一致）
"""
import io
import pandas as pd
import pytest

from src.services.dr007_service import DR007Service
from src.services.data_service import DataService


@pytest.mark.unit
def test_parse_csv_extracts_dr007_column():
    """解析：第 8 列（index 7）为当日 DR007 利率（%）"""
    csv_text = (
        "2026-08-22,1.6500,1.6500,1234,567.89,1.7000,1.6000,1.6500\n"
        "2026-08-21,1.6300,1.6300,1100,500.00,1.6800,1.5800,1.6300\n"
    )
    df = DR007Service.parse_csv(csv_text)

    assert list(df.columns) == ["date", "dr007"]
    assert len(df) == 2
    # parse_csv 按日期升序输出，所以 iloc[0] 是较早的 8/21，iloc[-1] 是最新 8/22
    assert df.iloc[0]["date"] == pd.Timestamp("2026-08-21")
    assert df.iloc[0]["dr007"] == pytest.approx(1.6300)
    assert df.iloc[-1]["date"] == pd.Timestamp("2026-08-22")
    assert df.iloc[-1]["dr007"] == pytest.approx(1.6500)


@pytest.mark.unit
def test_parse_csv_skips_invalid_rows():
    """解析：列数不足 / 第 8 列非 float → 跳过该行"""
    csv_text = (
        "2026-08-22,bad,1.6500\n"                              # 列数不足
        "2026-08-21,1.6300,1.6300,1234,500,1.7,1.6,1.6300\n"  # 合法
        "2026-08-20,1.6200,1.6200,1234,500,1.7,1.6,notnum\n"   # 第 8 列非 float
    )
    df = DR007Service.parse_csv(csv_text)

    assert len(df) == 1
    assert df.iloc[0]["date"] == pd.Timestamp("2026-08-21")


@pytest.mark.unit
def test_parse_csv_empty_input_returns_empty_df():
    """空输入 → 空 DataFrame（列结构不变）"""
    df = DR007Service.parse_csv("")
    assert list(df.columns) == ["date", "dr007"]
    assert len(df) == 0


@pytest.mark.unit
def test_parse_csv_sorts_by_date_ascending():
    """解析：CSV 倒序时按日期升序返回"""
    csv_text = (
        "2026-08-22,1.6500,1.6500,1,1,1.7,1.6,1.6500\n"
        "2026-08-19,1.6000,1.6000,1,1,1.7,1.6,1.6000\n"
        "2026-08-21,1.6300,1.6300,1,1,1.7,1.6,1.6300\n"
    )
    df = DR007Service.parse_csv(csv_text)

    assert df["date"].tolist() == [
        pd.Timestamp("2026-08-19"),
        pd.Timestamp("2026-08-21"),
        pd.Timestamp("2026-08-22"),
    ]


@pytest.mark.integration
def test_save_and_load_dr007_roundtrip(tmp_path):
    """save_dr007_data → load_dr007 能读回（首次写入）"""
    csv_path = tmp_path / "dr007.csv"
    df_to_write = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20", "2026-08-21", "2026-08-22"]),
        "dr007": [1.62, 1.63, 1.65],
    })

    service = DataService()
    service.save_dr007_data(df_to_write, path=csv_path)
    assert csv_path.exists()

    loaded = service.load_dr007(path=csv_path)
    assert len(loaded) == 3
    assert loaded["dr007"].iloc[-1] == pytest.approx(1.65)
    assert loaded["dr007"].iloc[0] == pytest.approx(1.62)


@pytest.mark.integration
def test_save_dr007_merges_with_existing_data(tmp_path):
    """save_dr007_data 与现有 CSV 合并（按 date 去重，新值覆盖旧值）"""
    csv_path = tmp_path / "dr007.csv"
    service = DataService()

    # 第一次写入
    first = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20", "2026-08-21"]),
        "dr007": [1.62, 1.63],
    })
    service.save_dr007_data(first, path=csv_path)

    # 第二次写入：含 1 条旧日期（覆盖）+ 1 条新日期
    second = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-21", "2026-08-22"]),
        "dr007": [1.99, 1.65],  # 8/21 应覆盖为 1.99
    })
    service.save_dr007_data(second, path=csv_path)

    loaded = service.load_dr007(path=csv_path)
    assert len(loaded) == 3
    # 验证合并：8/21 被新值覆盖
    assert loaded.loc[pd.Timestamp("2026-08-21"), "dr007"] == pytest.approx(1.99)
    assert loaded.loc[pd.Timestamp("2026-08-22"), "dr007"] == pytest.approx(1.65)


@pytest.mark.integration
def test_save_dr007_creates_file_with_header(tmp_path):
    """save_dr007_data 写入空 df 也能建带 header 的空文件"""
    csv_path = tmp_path / "dr007.csv"
    empty_df = pd.DataFrame(columns=["date", "dr007"])

    service = DataService()
    service.save_dr007_data(empty_df, path=csv_path)
    assert csv_path.exists()

    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert "date" in header
    assert "dr007" in header
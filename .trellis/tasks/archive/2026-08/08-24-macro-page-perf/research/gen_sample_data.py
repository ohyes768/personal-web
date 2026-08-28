"""合成宏观数据样本，用于本地实测 AC1/AC2。

真实数据在 NAS 服务器上（/var/lib/docker/volumes/macro-data/_data），
本地 backend/macro/data/ 是空的。跑这个脚本生成与真实 schema 一致的
12 个 CSV，覆盖：
  - 大体量（6000+ 行 × 多列）验证 gzip 压缩效果
  - 缺失 / NaN / 月度 vs 日度 各种边界

注意：
  - 数据是合成的，不能用于功能验证（用真实数据）
  - 仅供本任务的 AC1/AC2 本地实测

用法：
    python gen_sample_data.py [--rows N] [--out DIR]
    默认: 6200 行（≈16 年交易日），写到 ../data_sample/（临时目录，不进仓库）
"""
import argparse
import random
from pathlib import Path
import pandas as pd
import numpy as np


def gen_us_treasuries(rows: int, start: str = "2000-01-03") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=rows)
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "美债3m": rng.normal(2.5, 1.5, rows).round(4),
        "美债2y": rng.normal(3.0, 1.2, rows).round(4),
        "美债10y": rng.normal(4.0, 1.5, rows).round(4),
    }, index=dates)
    df.index.name = "date"
    return df


def gen_eu_bonds_monthly(rows: int, start: str = "2000-01-01") -> pd.DataFrame:
    # 真实数据是月度（每月 1 号），rows 控制约几年
    dates = pd.date_range(start, periods=rows, freq="MS")
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        "德债3m": rng.normal(1.5, 1.0, rows).round(4),
        "德债2y": rng.normal(2.0, 1.0, rows).round(4),
        "德债10y": rng.normal(2.8, 1.0, rows).round(4),
    }, index=dates)
    df.index.name = "date"
    return df


def gen_jp_bonds_monthly(rows: int, start: str = "2000-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=rows, freq="MS")
    rng = np.random.default_rng(11)
    df = pd.DataFrame({"日债10y": rng.normal(0.8, 0.6, rows).round(4)}, index=dates)
    df.index.name = "date"
    return df


def gen_exchange_rates(rows: int, start: str = "2000-01-03") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=rows)
    rng = np.random.default_rng(21)
    df = pd.DataFrame({
        "美元指数": rng.normal(95, 10, rows).round(4),
        "美元人民币": rng.normal(7.0, 1.5, rows).round(4),
        "美元日元": rng.normal(110, 20, rows).round(2),
        "美元欧元": rng.normal(1.1, 0.15, rows).round(4),
    }, index=dates)
    df.index.name = "date"
    return df


def gen_vix(rows: int, start: str = "2000-01-03") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=rows)
    rng = np.random.default_rng(33)
    df = pd.DataFrame({"Close_VIX": rng.normal(18, 8, rows).round(2)}, index=dates)
    df.index.name = "date"
    return df


def gen_fund_flow(rows: int, start: str = "2014-11-17") -> pd.DataFrame:
    # 北向 2014-11 才有真实数据，rows ≈ 2500 行 ≈ 10 年
    actual_rows = min(rows, 2500)
    dates = pd.bdate_range(start, periods=actual_rows)
    rng = np.random.default_rng(55)
    df = pd.DataFrame({
        "北向净流入": rng.normal(0, 50, actual_rows).round(2),
        "北向买入": rng.normal(100, 50, actual_rows).round(2),
        "北向卖出": rng.normal(100, 50, actual_rows).round(2),
        "南向净流入": rng.normal(0, 30, actual_rows).round(2),
        "南向买入": rng.normal(50, 30, actual_rows).round(2),
        "南向卖出": rng.normal(50, 30, actual_rows).round(2),
    }, index=dates)
    df.index.name = "date"
    return df


def gen_china_bond(rows: int, start: str = "2018-01-01") -> pd.DataFrame:
    actual_rows = min(rows, 2000)
    dates = pd.bdate_range(start, periods=actual_rows)
    rng = np.random.default_rng(77)
    df = pd.DataFrame({
        "中国国债收益率10年": rng.normal(3.2, 0.5, actual_rows).round(4),
        "中国国债收益率10年-2年": rng.normal(0.5, 0.3, actual_rows).round(4),
    }, index=dates)
    df.index.name = "date"
    return df


def gen_ted_spread(rows: int, start: str = "2012-01-01") -> pd.DataFrame:
    actual_rows = min(rows, 3500)
    dates = pd.bdate_range(start, periods=actual_rows)
    rng = np.random.default_rng(88)
    sofr = rng.normal(4.5, 1.5, actual_rows).round(4)
    us_3m = rng.normal(4.2, 1.5, actual_rows).round(4)
    df = pd.DataFrame({
        "SOFR": sofr,
        "美债3m": us_3m,
        "TED利差": sofr - us_3m,
    }, index=dates)
    df.index.name = "date"
    return df


def gen_commodities(rows: int, start: str = "2021-01-01") -> pd.DataFrame:
    # 阿里云 comkm 历史只 5 年
    actual_rows = min(rows, 1300)
    dates = pd.bdate_range(start, periods=actual_rows)
    rng = np.random.default_rng(101)
    df = pd.DataFrame({
        "黄金": rng.normal(450, 50, actual_rows).round(2),
        "白银": rng.normal(5500, 800, actual_rows).round(2),
        "原油": rng.normal(80, 15, actual_rows).round(2),
        "铜": rng.normal(9000, 1500, actual_rows).round(2),
    }, index=dates)
    df.index.name = "date"
    return df


def gen_indices(rows: int, start: str = "2021-01-01") -> pd.DataFrame:
    actual_rows = min(rows, 1300)
    dates = pd.bdate_range(start, periods=actual_rows)
    rng = np.random.default_rng(131)
    df = pd.DataFrame({
        "HKHSI": rng.normal(20000, 3000, actual_rows).round(2),
        "SH000001": rng.normal(3200, 400, actual_rows).round(2),
        "SPX": rng.normal(4500, 500, actual_rows).round(2),
        "IXIC": rng.normal(14000, 2000, actual_rows).round(2),
        "DJI": rng.normal(35000, 4000, actual_rows).round(2),
    }, index=dates)
    df.index.name = "date"
    return df


def gen_tga(rows: int, start: str = "2000-01-03") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=rows)
    rng = np.random.default_rng(151)
    df = pd.DataFrame({"Close_TGA": rng.normal(500_000, 200_000, rows).round(0)}, index=dates)
    df.index.name = "date"
    return df


def gen_hibor(rows: int, start: str = "2000-01-03") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=rows)
    rng = np.random.default_rng(177)
    df = pd.DataFrame({"HIBOR_Overnight": rng.normal(3.0, 1.5, rows).round(4)}, index=dates)
    df.index.name = "date"
    return df


GENERATORS = {
    "us_treasuries.csv": gen_us_treasuries,
    "eu_bonds.csv": lambda r: gen_eu_bonds_monthly(r // 12),
    "jp_bonds.csv": lambda r: gen_jp_bonds_monthly(r // 12),
    "exchange_rates.csv": gen_exchange_rates,
    "vix.csv": gen_vix,
    "fund_flow.csv": gen_fund_flow,
    "china_bond.csv": gen_china_bond,
    "ted_spread.csv": gen_ted_spread,
    "commodities.csv": gen_commodities,
    "indices.csv": gen_indices,
    "tga.csv": gen_tga,
    "hibor.csv": gen_hibor,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=6200, help="最长序列行数（≈16 年交易日）")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data_sample")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for name, gen in GENERATORS.items():
        df = gen(args.rows)
        path = args.out / name
        df.to_csv(path)
        print(f"  {name}: {len(df)} rows, {len(df.columns)} cols, {path.stat().st_size // 1024} KB")
    print(f"\n样本数据已生成 → {args.out}")
    print("用环境变量覆盖 data_dir：  set MACRO_DATA_DIR=" + str(args.out.resolve()))
    print("Linux/Mac:  export MACRO_DATA_DIR=" + str(args.out.resolve()))


if __name__ == "__main__":
    main()
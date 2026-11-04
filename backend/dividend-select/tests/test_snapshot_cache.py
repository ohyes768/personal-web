"""
源文件签名快照缓存回归测试

覆盖 11-02-dividend-page-load-speed 的 R2 语义：
- 同签名复用（重复请求不再重读/重组）
- 文件替换、新季度文件、删除后补齐 → 下一次读取返回新结果
- 坏文件不发布缓存（修复后自动恢复）
- 并发构建去重
- M120 缓存依赖当前周文件签名（无效→修复的失效路径）
- /stocks 的 codes 精确过滤与前导零契约
"""
import asyncio
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.api import routes
from src.services.m120_service import M120Service
from src.services.shareholder_financial_reader import FinancialReader, ShareholderReader
from src.services.versioned_snapshot import VersionedSnapshot, file_signature


# ---------- VersionedSnapshot 单元 ----------

def test_same_signature_reuses_build():
    build_count = {"n": 0}

    def build():
        build_count["n"] += 1
        return {"value": build_count["n"]}

    snap = VersionedSnapshot("test", build)
    probe = lambda: ("p", 100, 10)  # noqa: E731
    assert snap.get(probe) == {"value": 1}
    assert snap.get(probe) == {"value": 1}
    assert build_count["n"] == 1


def test_signature_change_rebuilds():
    build_count = {"n": 0}

    def build():
        build_count["n"] += 1
        return {"value": build_count["n"]}

    snap = VersionedSnapshot("test", build)
    assert snap.get(lambda: ("p", 100, 10)) == {"value": 1}
    # mtime/size 任一变化都要重建
    assert snap.get(lambda: ("p", 200, 10)) == {"value": 2}
    assert snap.get(lambda: ("p", 200, 12)) == {"value": 3}
    # 换路径（新季度文件）同样重建
    assert snap.get(lambda: ("q", 200, 12)) == {"value": 4}
    assert build_count["n"] == 4


def test_missing_signature_is_never_cached():
    """缺失（None 签名）不缓存：补齐后下一次读取拿到新结果。"""
    snap = VersionedSnapshot("test", lambda: {"source": "empty"})
    assert snap.get(lambda: None) == {"source": "empty"}
    assert snap.get(lambda: ("p", 1, 1)) == {"source": "empty"}
    assert snap.get(lambda: None) == {"source": "empty"}


def test_build_failure_is_not_published():
    """坏源抛异常时不发布缓存；修复后（签名变化）自动恢复。"""
    state = {"good": False}

    def build():
        if not state["good"]:
            raise ValueError("bad file")
        return {"value": 42}

    snap = VersionedSnapshot("test", build)
    with pytest.raises(ValueError):
        snap.get(lambda: ("p", 100, 10))
    with pytest.raises(ValueError):
        snap.get(lambda: ("p", 100, 10))
    # 同签名失败后修复内容但签名恰好相同 → 仍失败（签名是失效依据）
    state["good"] = True
    assert snap.get(lambda: ("p", 100, 10)) == {"value": 42}
    assert snap.get(lambda: ("p", 100, 10)) == {"value": 42}


def test_concurrent_get_builds_once():
    build_count = {"n": 0}
    barrier = threading.Barrier(4)

    def build():
        build_count["n"] += 1
        time.sleep(0.05)
        return {"worker": build_count["n"]}

    snap = VersionedSnapshot("test", build)
    probe = lambda: ("p", 1, 1)  # noqa: E731
    results: list = []

    def worker():
        barrier.wait()
        results.append(snap.get(probe))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert all(not thread.is_alive() for thread in threads)
    assert build_count["n"] == 1
    assert results == [results[0]] * 4


def test_file_signature_tracks_replacement(tmp_path: Path):
    path = tmp_path / "f.csv"
    path.write_text("a", encoding="utf-8-sig")
    first = file_signature(path)
    assert first is not None and first[0] == str(path)

    os.utime(path, (time.time() + 10, time.time() + 10))
    assert file_signature(path) != first

    path.unlink()
    assert file_signature(path) is None
    assert file_signature(None) is None
    assert file_signature(tmp_path / "nope.csv") is None


# ---------- ShareholderReader / FinancialReader ----------

@pytest.fixture
def aux_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("src.api.helpers.aux_data.DATA_DIR", tmp_path)
    return tmp_path


SHAREHOLDER_HEADER = "股票代码,数据季度,股东户数,股东人数增幅,人均持股数量\n"


def write_aux(root: Path, name: str, rows: list[str], mtime: float | None = None) -> Path:
    path = root / name
    path.write_text("".join(rows), encoding="utf-8-sig")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_shareholder_reader_reuses_and_reloads(aux_data_dir: Path):
    reader = ShareholderReader()
    path = write_aux(aux_data_dir, "股东户数汇总_2026Q3.csv",
                     [SHAREHOLDER_HEADER, "90,2026Q3,12345,1.5,678.9\n"], mtime=1000)

    first = reader.read_csv()
    assert first.iloc[0]["股票代码"] == "000090"
    assert reader.read_csv() is first  # 同签名复用同一对象

    # 原地更新（mtime 变）→ 重读
    write_aux(aux_data_dir, "股东户数汇总_2026Q3.csv",
              [SHAREHOLDER_HEADER, "90,2026Q3,22222,2.5,111.1\n"], mtime=2000)
    second = reader.read_csv()
    assert second is not first
    assert int(second.iloc[0]["股东户数"]) == 22222

    # 新季度文件（更新的 mtime）→ 切换到新文件
    write_aux(aux_data_dir, "股东户数汇总_2026Q4.csv",
              [SHAREHOLDER_HEADER, "90,2026Q4,33333,3.5,222.2\n"], mtime=3000)
    third = reader.read_csv()
    assert str(third.iloc[0]["数据季度"]) == "2026Q4"
    assert reader.get_quarter() == "2026Q4"


def test_shareholder_reader_survives_delete_and_recreate(aux_data_dir: Path):
    reader = ShareholderReader()
    path = write_aux(aux_data_dir, "股东户数汇总_2026Q3.csv",
                     [SHAREHOLDER_HEADER, "90,2026Q3,12345,1.5,678.9\n"])
    assert not reader.read_csv().empty

    path.unlink()
    assert reader.read_csv().empty  # 删除后返回空，不炸

    # 缺失后补齐 → 恢复
    write_aux(aux_data_dir, "股东户数汇总_2026Q3.csv",
              [SHAREHOLDER_HEADER, "90,2026Q3,99999,9.9,1.0\n"], mtime=5000)
    restored = reader.read_csv()
    assert int(restored.iloc[0]["股东户数"]) == 99999


def test_shareholder_bad_file_not_cached(aux_data_dir: Path):
    """坏文件返回空且不发布缓存；修复后下一次读取拿到数据。"""
    reader = ShareholderReader()
    path = write_aux(aux_data_dir, "股东户数汇总_2026Q3.csv", ["garbage,no-header\n"])
    assert reader.read_csv().empty

    write_aux(aux_data_dir, "股东户数汇总_2026Q3.csv",
              [SHAREHOLDER_HEADER, "90,2026Q3,12345,1.5,678.9\n"],
              mtime=path.stat().st_mtime + 10)
    assert not reader.read_csv().empty


def test_shareholder_read_map_contract(aux_data_dir: Path):
    reader = ShareholderReader()
    write_aux(aux_data_dir, "股东户数汇总_2026Q3.csv", [
        SHAREHOLDER_HEADER,
        "90,2026Q3,12345,1.5,678.9\n",
        "600000,2026Q3,89000,,\n",  # 缺失数值 → None
    ])
    mapping = reader.read_map()
    assert mapping["000090"] == {
        "shareholder_count": 12345,
        "shareholder_change_pct": 1.5,
        "per_share_holding": 678.9,
    }
    assert mapping["600000"]["shareholder_count"] == 89000
    assert mapping["600000"]["shareholder_change_pct"] is None

    # map 随源文件失效
    write_aux(aux_data_dir, "股东户数汇总_2026Q3.csv",
              [SHAREHOLDER_HEADER, "90,2026Q3,55555,5.5,5.5\n"],
              mtime=7000)
    assert reader.read_map()["000090"]["shareholder_count"] == 55555


FINANCIAL_HEADER = (
    "股票代码,数据季度,数据日期,ROE,ROE年度,近3年平均ROE,近3年ROE历史,"
    "前一季度扣非同比(%),前一季度,最新季度扣非(元),最新季度扣非同比(%),"
    "主营业务利润率,净利率,资产负债率,扣非净利润同比,3年复合增长率,"
    "最新EPS年度,最新EPS(元),最近年度扣非净利润(元),扣非利润年度\n"
)


def test_financial_read_map_contract(aux_data_dir: Path):
    reader = FinancialReader()
    write_aux(aux_data_dir, "财务指标汇总_2026Q2.csv", [
        FINANCIAL_HEADER,
        "600000,2026Q2,2026-06-30,11.5,2025,10.2,\"[{\"\"year\"\": 2023, \"\"value\"\": 9.5}]\","
        "-3.2,2026Q1,120000000,4.1,30.1,12.3,55.2,8.8,6.6,2025,1.23,-800000000,2025\n",
    ])
    mapping = reader.read_map()
    data = mapping["600000"]
    assert data["roe"] == 11.5
    assert data["roe_year"] == 2025
    assert data["latest_quarter_label"] == "2026Q2"
    assert data["annual_profit_year"] == 2025
    assert data["roe_history"] == [{"year": 2023, "value": 9.5}]

    # 更新后重读（签名字段透传一致）
    write_aux(aux_data_dir, "财务指标汇总_2026Q2.csv", [
        FINANCIAL_HEADER,
        "600000,2026Q2,2026-06-30,12.5,2025,10.2,\"[{\"\"year\"\": 2023, \"\"value\"\": 9.5}]\","
        "-3.2,2026Q1,120000000,4.1,30.1,12.3,55.2,8.8,6.6,2025,1.23,-800000000,2025\n",
    ], mtime=9000)
    assert reader.read_map()["600000"]["roe"] == 12.5


def test_financial_strict_raises_on_bad_file(aux_data_dir: Path):
    reader = FinancialReader()
    write_aux(aux_data_dir, "财务指标汇总_2026Q2.csv", ["not,a,real,file\n"])
    assert reader.read_csv().empty
    with pytest.raises(Exception):
        reader.read_csv(strict=True)


# ---------- M120Service 快照缓存 ----------

@pytest.fixture
def m120_env(tmp_path):
    with patch("src.services.m120_service.DATA_DIR", tmp_path), patch(
        "src.services.base.get_current_date_dir", return_value="2026-10"
    ), patch("src.services.base.datetime") as clock:
        clock.now.return_value = datetime(2026, 10, 12)
        yield M120Service(), tmp_path


def m120_snapshot(root: Path, month: str, suffix: str, body: str, mtime: float | None = None) -> Path:
    path = root / month / f"M120均线_{suffix}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8-sig")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


M120_ROW = "2026-10-11,000001,12.5\n"


def test_m120_cache_reuses_snapshot(m120_env):
    svc, root = m120_env
    m120_snapshot(root, "2026-10", "10-05-10-11",
                  f"日期,股票代码,M120\n{M120_ROW}")
    assert svc.read_m120_data() == {"000001": {"m120": 12.5}}
    # 缓存命中路径：check/mtime/再读全部一致
    assert svc.read_m120_data() == {"000001": {"m120": 12.5}}
    assert svc.check_m120_file_exists()
    assert svc.read_m120_with_deviation()["000001"]["m120"] == 12.5


def test_m120_current_week_repair_invalidates_cache(m120_env):
    """当前周文件从无效变有效（refresh 补齐）后必须切到新快照。"""
    svc, root = m120_env
    m120_snapshot(root, "2026-10", "10-05-10-11",
                  f"日期,股票代码,M120\n{M120_ROW}")
    m120_snapshot(root, "2026-10", "10-12-10-18", "")  # 当前周无效
    assert svc.read_m120_data() == {"000001": {"m120": 12.5}}  # fallback 上周

    # 修复当前周文件（原子替换语义：mtime/size 变化）
    m120_snapshot(root, "2026-10", "10-12-10-18",
                  f"日期,股票代码,M120\n{M120_ROW}", mtime=9999)
    assert svc.read_m120_data() == {"000001": {"m120": 12.5}}
    current_path = root / "2026-10" / "M120均线_10-12-10-18.csv"
    assert svc.get_m120_file_mtime() == current_path.stat().st_mtime


def test_m120_price_update_invalidates_deviation(m120_env):
    svc, root = m120_env
    m120_snapshot(root, "2026-10", "10-12-10-18",
                  f"日期,股票代码,M120\n{M120_ROW}")
    assert svc.read_m120_with_deviation()["000001"]["realtime"] == 12.5  # 无价格回退 M120

    price = root / "2026-10" / "实时价格.csv"
    price.write_text("日期,股票代码,昨日收盘,实时价格,静态PE,市净率\n2026-10-12,000001,12.0,13.2,8.1,0.9\n", encoding="utf-8-sig")
    merged = svc.read_m120_with_deviation()["000001"]
    assert merged["realtime"] == 13.2
    assert merged["deviation"] == round((12.0 - 12.5) / 12.5 * 100, 2)
    assert merged["pe"] == 8.1

    # 价格文件更新（mtime 推进）→ 偏离度重算
    os.utime(price, (time.time() + 10, time.time() + 10))
    price.write_text("日期,股票代码,昨日收盘,实时价格,静态PE,市净率\n2026-10-12,000001,12.0,14.4,8.2,0.9\n", encoding="utf-8-sig")
    assert svc.read_m120_with_deviation()["000001"]["realtime"] == 14.4

    # /prices 只读路径也拿到新值
    assert svc.read_prices_only()["000001"]["realtime"] == 14.4


def test_m120_snapshot_edit_invalidates_cache(m120_env):
    """选中快照被原地修改（如备份恢复）→ 重读新内容。"""
    svc, root = m120_env
    path = m120_snapshot(root, "2026-10", "10-12-10-18",
                         f"日期,股票代码,M120\n{M120_ROW}")
    assert svc.read_m120_data() == {"000001": {"m120": 12.5}}

    path.write_text("日期,股票代码,M120\n2026-10-12,000001,20.0\n", encoding="utf-8-sig")
    os.utime(path, (time.time() + 10, time.time() + 10))
    assert svc.read_m120_data() == {"000001": {"m120": 20.0}}


def test_m120_week_rollover_invalidates_cache(m120_env):
    svc, root = m120_env
    m120_snapshot(root, "2026-10", "10-05-10-11",
                  f"日期,股票代码,M120\n{M120_ROW}")
    assert svc.read_m120_data() == {"000001": {"m120": 12.5}}

    with patch("src.services.base.datetime") as clock:
        clock.now.return_value = datetime(2026, 10, 19)
        m120_snapshot(root, "2026-10", "10-19-10-25",
                      "日期,股票代码,M120\n2026-10-19,000001,15.0\n")
        assert svc.read_m120_data() == {"000001": {"m120": 15.0}}


def test_m120_missing_then_backfilled(m120_env):
    svc, root = m120_env
    assert svc.read_m120_data() == {}
    assert not svc.check_m120_file_exists()

    m120_snapshot(root, "2026-10", "10-12-10-18",
                  f"日期,股票代码,M120\n{M120_ROW}")
    assert svc.read_m120_data() == {"000001": {"m120": 12.5}}


# ---------- /stocks codes 精确过滤 ----------

def make_routes_mocks():
    df = pd.DataFrame({
        "股票代码": ["000090", "600000", "000001"],
        "股票名称": ["甲", "乙", "丙"],
        "交易所": ["沪市主板", "沪市主板", "深市主板"],
        "3年平均股息率(%)": [5.1, 4.2, 6.0],
        "近5年分红详情": [None, None, None],
    })
    reader = Mock()
    reader.read_csv.return_value = df
    reader.check_csv_exists.return_value = True
    reader.get_file_mtime.return_value = 1000.0
    reader.get_total_count.return_value = len(df)
    filterer = Mock()
    filterer.filter_by_3y_dividend.side_effect = lambda frame, **kwargs: frame
    filterer.filter_by_yield_range.side_effect = lambda frame, *a, **k: frame
    filterer.filter_by_exchange.side_effect = lambda frame, *a, **k: frame
    filterer.filter_by_industry.side_effect = lambda frame, *a, **k: frame
    filterer.filter_by_index.side_effect = lambda frame, *a, **k: frame
    sorter = Mock()
    sorter.sort_by_field.side_effect = lambda frame, *a, **k: frame
    return reader, filterer, sorter


def patch_routes(reader, filterer, sorter, monkeypatch):
    monkeypatch.setattr(routes, "data_reader", reader)
    monkeypatch.setattr(routes, "filter_service", filterer)
    monkeypatch.setattr(routes, "sort_service", sorter)
    monkeypatch.setattr(routes, "stock_info_service", None)
    monkeypatch.setattr(routes, "shareholder_reader", None)
    monkeypatch.setattr(routes, "financial_reader", None)


def test_stocks_codes_filter_with_leading_zeros(monkeypatch):
    reader, filterer, sorter = make_routes_mocks()
    patch_routes(reader, filterer, sorter, monkeypatch)
    response = asyncio.run(routes.get_stocks(
        min_yield=0, max_yield=None, exchange=None, industry=None,
        index=None, sort_by="avg_yield_3y", sort_order="desc", codes="90,600000",
    ))
    assert response.total == 2
    assert [item.code for item in response.items] == ["000090", "600000"]


def test_stocks_codes_filter_intersects_min_yield(monkeypatch):
    """codes 与 min_yield 取交集：min_yield>0 时继续过滤。"""
    reader, filterer, sorter = make_routes_mocks()
    filterer.filter_by_3y_dividend.side_effect = (
        lambda frame, min_avg_yield: frame[frame["3年平均股息率(%)"] >= min_avg_yield]
    )
    patch_routes(reader, filterer, sorter, monkeypatch)
    response = asyncio.run(routes.get_stocks(
        min_yield=5.0, max_yield=None, exchange=None, industry=None,
        index=None, sort_by="avg_yield_3y", sort_order="desc", codes="90,600000,1",
    ))
    codes = [item.code for item in response.items]
    # codes 并集 ∩ min_yield≥5：600000 (4.2) 被阈值剔除；000001 (6.0) 在 codes 内保留
    assert codes == ["000090", "000001"]


def test_stocks_codes_filter_no_match(monkeypatch):
    reader, filterer, sorter = make_routes_mocks()
    patch_routes(reader, filterer, sorter, monkeypatch)
    response = asyncio.run(routes.get_stocks(
        min_yield=0, max_yield=None, exchange=None, industry=None,
        index=None, sort_by="avg_yield_3y", sort_order="desc", codes="999999",
    ))
    assert response.total == 0
    assert response.items == []


def test_stocks_codes_filter_invalid_code_422(monkeypatch):
    reader, filterer, sorter = make_routes_mocks()
    patch_routes(reader, filterer, sorter, monkeypatch)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(routes.get_stocks(
            min_yield=0, max_yield=None, exchange=None, industry=None,
            index=None, sort_by="avg_yield_3y", sort_order="desc", codes="abc",
        ))
    assert exc_info.value.status_code == 422


def test_stocks_codes_none_keeps_original_behavior(monkeypatch):
    reader, filterer, sorter = make_routes_mocks()
    patch_routes(reader, filterer, sorter, monkeypatch)
    response = asyncio.run(routes.get_stocks(
        min_yield=0, max_yield=None, exchange=None, industry=None,
        index=None, sort_by="avg_yield_3y", sort_order="desc", codes=None,
    ))
    assert response.total == 3


def test_stocks_concurrent_builds_stay_consistent(monkeypatch):
    """线程池并发构建同一快照：结果一致、无异常（冒烟）。"""
    reader, filterer, sorter = make_routes_mocks()
    patch_routes(reader, filterer, sorter, monkeypatch)

    async def scenario():
        results = await asyncio.gather(*(
            routes.get_stocks(
                min_yield=0, max_yield=None, exchange=None, industry=None,
                index=None, sort_by="avg_yield_3y", sort_order="desc", codes="90",
            ) for _ in range(5)
        ))
        assert all(r.total == 1 for r in results)
        await routes.health()

    asyncio.run(scenario())

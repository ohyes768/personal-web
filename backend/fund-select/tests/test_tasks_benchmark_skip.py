"""
_refresh_fund_benchmarks 的 QDII 跳过逻辑（PRD 09-03-qdii-skip-benchmark）。

为什么：QDII/互认基准公式（MSCI、标普全球等）无免费数据源，fallback 出的
中证800 基准是错误口径 → 直接跳过合成，写 tri=NULL，界面 5 列显示 -。
"""
from datetime import date

import pandas as pd
import pytest

from src.db.models import Fund, FundBenchmark
from src.scheduler.tasks import _refresh_fund_benchmarks
from tests.conftest import _mk_fund


@pytest.fixture
def mock_benchmark(monkeypatch):
    """fetch_benchmark_tri 打桩：返回 2 行 TRI；QDII 不应触发（触发即 fail）。"""
    called: list[str] = []

    def _fake_fetch(code, start, end):
        called.append(code)
        df = pd.DataFrame({
            "date": pd.to_datetime([date(2026, 9, 1), date(2026, 9, 2)]),
            "tri": [1000.0, 1001.0],
        })
        return df, "fetched"

    monkeypatch.setattr("src.data.benchmark_fetcher.fetch_benchmark_tri", _fake_fetch)
    monkeypatch.setattr("src.data.benchmark_fetcher.clear_index_cache", lambda: None)
    return called


def _rows(db, code: str) -> list[FundBenchmark]:
    return db.query(FundBenchmark).filter(FundBenchmark.code == code).all()


def test_qdii_fund_skipped_with_null_tri(db_session, mock_benchmark):
    """QDII 基金：不调 fetch_benchmark_tri，写单行 tri=NULL source=skipped:qdii。"""
    db_session.add(_mk_fund("270042", fund_type="QDII-股票"))
    db_session.commit()

    errors = _refresh_fund_benchmarks(db_session, ["270042"])

    assert errors == []
    assert mock_benchmark == []                       # 未触发真实/打桩 fetch
    rows = _rows(db_session, "270042")
    assert len(rows) == 1
    assert rows[0].tri is None
    assert rows[0].source == "skipped:qdii"


def test_mutual_recognition_fund_skipped(db_session, mock_benchmark):
    """互认基金（fund_type 不以 QDII 开头）同样跳过。"""
    db_session.add(_mk_fund("968157", fund_type="互认基金"))
    db_session.commit()

    _refresh_fund_benchmarks(db_session, ["968157"])

    assert mock_benchmark == []
    rows = _rows(db_session, "968157")
    assert len(rows) == 1 and rows[0].tri is None
    assert rows[0].source == "skipped:qdii"


def test_non_qdii_fund_still_fetches(db_session, mock_benchmark):
    """非 QDII：行为不变，正常合成 TRI 入库。"""
    db_session.add(_mk_fund("671030", fund_type="股票型-偏股"))
    db_session.commit()

    errors = _refresh_fund_benchmarks(db_session, ["671030"])

    assert errors == []
    assert mock_benchmark == ["671030"]
    rows = _rows(db_session, "671030")
    assert len(rows) == 2 and rows[0].source == "fetched"


def test_skip_replaces_stale_benchmark_rows(db_session, mock_benchmark):
    """跳过要幂等覆盖旧数据：库内已有的 fallback 旧基准行必须清掉。"""
    db_session.add(_mk_fund("486002", fund_type="QDII"))
    db_session.add_all([
        FundBenchmark(code="486002", date=date(2026, 8, 1), tri=1000.0, source="fallback_chain:sh000906"),
        FundBenchmark(code="486002", date=date(2026, 8, 2), tri=1002.0, source="fallback_chain:sh000906"),
    ])
    db_session.commit()

    _refresh_fund_benchmarks(db_session, ["486002"])

    rows = _rows(db_session, "486002")
    assert len(rows) == 1 and rows[0].source == "skipped:qdii"


def test_fund_type_null_treated_as_non_qdii(db_session, mock_benchmark):
    """fund_type 为空的基金不跳过（与 exclude_qdii 口径一致：NULL 保留）。"""
    db_session.add(Fund(code="100001", name="基金X", is_active=True))
    db_session.commit()

    _refresh_fund_benchmarks(db_session, ["100001"])

    assert mock_benchmark == ["100001"]

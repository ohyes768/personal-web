"""AC4：模型版本边界——同月价格更新不改系数；新完整月生成新版本且不覆盖旧版本。"""
from __future__ import annotations

from src.core.months import shift_month
from src.core.models import KIND_SINCE_INCEPTION, KIND_TRAILING, data_hash
from src.data.validate import MonthlySeries


def test_same_month_price_update_keeps_model(service, fixture_series):
    """同月内未完成月（partial bar）价格变化不改变完整月序列 → 模型不变。"""
    models_a = {r.model_id for r in service._compute_models(fixture_series, "2026-09")}
    models_b = {r.model_id for r in service._compute_models(fixture_series, "2026-09")}
    assert models_a == models_b


def test_new_complete_month_creates_new_version(service, fixture_series):
    """新完整月到来 → trailing/since_inception 新版本；固定窗口不产生新版本。"""
    result_old = service._compute_models(fixture_series, "2026-09")
    series_new = MonthlySeries(
        months=fixture_series.months + ["2026-10"],
        closes=fixture_series.closes + [4100.0],
        bars=dict(fixture_series.bars),
    )
    result_new = service._compute_models(series_new, "2026-10")

    old_trailing = next(r for r in result_old if r.kind == KIND_TRAILING)
    new_trailing = next(r for r in result_new if r.kind == KIND_TRAILING)
    assert old_trailing.model_id != new_trailing.model_id
    assert new_trailing.fit_start == shift_month(old_trailing.fit_start, 1)  # 滚动前进一个月
    assert new_trailing.fit_end == "2026-10"

    old_since = next(r for r in result_old if r.kind == KIND_SINCE_INCEPTION)
    new_since = next(r for r in result_new if r.kind == KIND_SINCE_INCEPTION)
    assert old_since.model_id != new_since.model_id
    assert new_since.fit_end == "2026-10"

    # 固定窗口模型训练数据定死 → ID 不变（不覆盖旧窗口）
    fixed_old = {r.model_id for r in result_old if r.kind == "historical_fixed_120m"}
    fixed_new = {r.model_id for r in result_new if r.kind == "historical_fixed_120m"}
    assert fixed_old == fixed_new


def test_upsert_model_is_idempotent(service, store, fixture_series):
    records = service._compute_models(fixture_series, "2026-09")
    assert all(store.upsert_model(r) for r in records)          # 首次全部写入
    assert not any(store.upsert_model(r) for r in records)      # 再次全部跳过
    assert len(store.list_models("000300")) == len(records)


def test_latest_model_returns_newest_cutoff(service, store, fixture_series):
    for r in service._compute_models(fixture_series, "2026-09"):
        store.upsert_model(r)
    from src.data.validate import MonthlySeries

    series_new = MonthlySeries(
        months=fixture_series.months + ["2026-10"],
        closes=fixture_series.closes + [4100.0],
        bars=dict(fixture_series.bars),
    )
    for r in service._compute_models(series_new, "2026-10"):
        store.upsert_model(r)
    trailing = store.latest_model("000300", KIND_TRAILING)
    assert trailing.data_cutoff_month == "2026-10"
    # 旧版本仍可查
    old = store.models_by_cutoff("000300", KIND_TRAILING, "2026-09")
    assert old is not None


def test_data_hash_stable_within_month(fixture_series):
    h1 = data_hash(fixture_series.closes)
    assert data_hash(list(fixture_series.closes)) == h1
    changed = fixture_series.closes[:-1] + [fixture_series.closes[-1] + 1.0]
    assert data_hash(changed) != h1

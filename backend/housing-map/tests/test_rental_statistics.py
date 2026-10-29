"""租金统计纯函数测试（离线，无 IO，fixture 内联构造样本）。"""
import datetime as dt
import math

import pytest

from src.services.rental_reference.statistics import (
    area_band_for,
    bedrooms_of,
    compute_rental_statistics,
    estimate_yield,
    is_stale,
)


def sample(id='1', *, rent=9000.0, area=100.0, layout='3室2厅', mode='whole',
           community_id='2010067741', flags=(), prop_type='住宅', detail=True,
           floor='5', captured_at='2026-10-01T10:00:00+00:00'):
    return {
        'source': 'fang',
        'source_listing_id': id,
        'source_url': f'https://zu.fang.com/hz/chuzu/{id}.htm',
        'source_community_id': community_id,
        'community_name': '风雅钱塘',
        'title': '出租',
        'monthly_rent_yuan': rent,
        'area_m2': area,
        'layout': layout,
        'rental_mode': mode,
        'price_kind': 'listing_rent',
        'published_at': None,
        'address': None,
        'property_type': prop_type,
        'quality_flags': list(flags),
        'detail_fetched': detail,
        'floor': floor,
        'captured_at': captured_at,
    }


def three_valid():
    return [
        sample('A', rent=9000.0, area=100.0, floor='3'),
        sample('B', rent=7500.0, area=100.0, floor='5'),
        sample('C', rent=12000.0, area=120.0, floor='7'),
    ]


def group_of(result, band, bedrooms):
    matches = [g for g in result['groups']
               if g['area_band'] == band and g['bedrooms'] == bedrooms]
    assert len(matches) <= 1
    return matches[0] if matches else None


# --- 分组边界 ---

def test_area_band_boundaries():
    assert area_band_for(89.9) == 'lt90'
    assert area_band_for(90.0) == '90to144'
    assert area_band_for(143.9) == '90to144'
    assert area_band_for(144.0) == 'gte144'


def test_area_band_invalid_inputs():
    assert area_band_for(0) is None
    assert area_band_for(-1) is None
    assert area_band_for(None) is None
    assert area_band_for(float('nan')) is None


def test_bedrooms_of_layouts():
    assert bedrooms_of('3室2厅') == 3
    assert bedrooms_of('2室') == 2
    assert bedrooms_of('5户合租') is None
    assert bedrooms_of(None) is None


# --- 单位换算与组指标 ---

def test_unit_rent_is_per_listing_conversion():
    result = compute_rental_statistics(three_valid())
    group = group_of(result, '90to144', 3)
    assert group['sample_count'] == 3
    ref = group['rent_reference']
    assert ref['median_unit_rent_yuan_m2_month'] == pytest.approx(90.0)
    assert ref['median_monthly_rent_yuan'] == pytest.approx(9000.0)


def test_median_unit_rent_uses_per_listing_conversion_not_ratio_of_medians():
    rows = [
        sample('U1', rent=9000.0, area=100.0, floor='1'),
        sample('U2', rent=8000.0, area=95.0, floor='2'),
        sample('U3', rent=13000.0, area=130.0, floor='3'),
        sample('U4', rent=10000.0, area=120.0, floor='4'),
    ]
    ref = group_of(compute_rental_statistics(rows), '90to144', 3)['rent_reference']
    expected = sorted([90.0, 8000.0 / 95.0, 100.0, 10000.0 / 120.0])
    assert ref['median_unit_rent_yuan_m2_month'] == pytest.approx(
        (expected[1] + expected[2]) / 2)
    assert ref['median_unit_rent_yuan_m2_month'] != pytest.approx(9500.0 / 110.0)


def test_percentile_linear_interpolation_and_even_median():
    rows = [
        sample('P1', rent=1000.0, area=100.0, floor='1'),
        sample('P2', rent=2000.0, area=100.0, floor='2'),
        sample('P3', rent=3000.0, area=100.0, floor='3'),
        sample('P4', rent=4000.0, area=100.0, floor='4'),
    ]
    ref = group_of(compute_rental_statistics(rows), '90to144', 3)['rent_reference']
    assert ref['p25_unit_rent_yuan_m2_month'] == pytest.approx(17.5)
    assert ref['p75_unit_rent_yuan_m2_month'] == pytest.approx(32.5)
    assert ref['median_unit_rent_yuan_m2_month'] == pytest.approx(25.0)
    assert ref['median_monthly_rent_yuan'] == pytest.approx(2500.0)


def test_all_bedrooms_band_is_recomputed_not_averaged():
    rows = [
        sample('W1', rent=3000.0, area=100.0, layout='2室1厅', floor='1'),
        sample('W2', rent=4000.0, area=100.0, layout='2室1厅', floor='2'),
        sample('W3', rent=5000.0, area=100.0, layout='2室1厅', floor='3'),
        sample('W4', rent=1200.0, area=120.0, layout='3室2厅', floor='1'),
        sample('W5', rent=1440.0, area=120.0, layout='3室2厅', floor='2'),
        sample('W6', rent=1680.0, area=120.0, layout='3室2厅', floor='3'),
    ]
    result = compute_rental_statistics(rows)
    two = group_of(result, '90to144', 2)['rent_reference']
    three = group_of(result, '90to144', 3)['rent_reference']
    merged_group = group_of(result, '90to144', None)
    merged = merged_group['rent_reference']
    assert two['median_unit_rent_yuan_m2_month'] == pytest.approx(40.0)
    assert three['median_unit_rent_yuan_m2_month'] == pytest.approx(12.0)
    assert merged['median_unit_rent_yuan_m2_month'] == pytest.approx((14.0 + 30.0) / 2)
    assert merged['median_unit_rent_yuan_m2_month'] != pytest.approx((40.0 + 12.0) / 2)
    assert merged_group['sample_count'] == 6


def test_groups_per_area_band_and_bedrooms():
    rows = [
        sample('B1', rent=4000.0, area=89.9, layout='2室1厅', floor='1'),
        sample('B2', rent=4400.0, area=89.9, layout='2室1厅', floor='2'),
        sample('B3', rent=4800.0, area=89.9, layout='2室1厅', floor='3'),
        sample('B4', rent=15000.0, area=144.0, layout='4室2厅', floor='1'),
        sample('B5', rent=16000.0, area=144.0, layout='4室2厅', floor='2'),
        sample('B6', rent=17000.0, area=144.0, layout='4室2厅', floor='3'),
    ]
    result = compute_rental_statistics(rows)
    lt90 = group_of(result, 'lt90', 2)
    gte144 = group_of(result, 'gte144', 4)
    assert lt90['sample_count'] == 3
    assert lt90['rent_reference']['median_monthly_rent_yuan'] == pytest.approx(4400.0)
    assert gte144['sample_count'] == 3
    assert group_of(result, '90to144', 3) is None
    assert group_of(result, 'lt90', None)['sample_count'] == 3


def test_insufficient_samples_have_null_reference_but_keep_details():
    rows = [
        sample('S1', rent=9000.0, area=100.0, floor='1'),
        sample('S2', rent=7500.0, area=100.0, floor='2'),
    ]
    group = group_of(compute_rental_statistics(rows), '90to144', 3)
    assert group['sample_count'] == 2
    assert group['rent_reference'] is None
    assert len(group['candidates']) == 2


def test_non_finite_values_never_reach_group_outputs():
    rows = [sample('N1', rent=float('inf')), *three_valid()]
    result = compute_rental_statistics(rows)
    group = group_of(result, '90to144', 3)
    assert group['sample_count'] == 3
    assert all(math.isfinite(value) for value in group['rent_reference'].values())


# --- 去重与疑似重复 ---

def test_duplicate_source_listing_ids_kept_once():
    rows = [*three_valid(), sample('A', rent=9000.0, area=100.0, floor='3')]
    result = compute_rental_statistics(rows)
    assert result['duplicate_source_ids_skipped'] == 1
    assert group_of(result, '90to144', 3)['sample_count'] == 3


def test_suspect_duplicates_flagged_and_excluded_from_counts():
    rows = [
        sample('D1', rent=9000.0, area=100.0, floor='5'),
        sample('D2', rent=9000.0, area=100.0, floor='5'),
        sample('D3', rent=9000.0, area=100.0, floor='6'),
    ]
    result = compute_rental_statistics(rows)
    assert len(result['suspect_duplicates']) == 1
    assert result['suspect_duplicates'][0]['duplicate_of'] == 'D1'
    assert result['suspect_duplicates'][0]['sample']['source_listing_id'] == 'D2'
    group = group_of(result, '90to144', 3)
    assert group['sample_count'] == 2
    assert group['rent_reference'] is None


# --- 排除理由 ---

def test_exclusion_reasons_are_enumerated():
    rows = [
        sample('X1', mode='shared'),
        sample('X2', rent=None),
        sample('X3', rent=0.0),
        sample('X4', area=-5.0),
        sample('X5', rent=float('nan')),
        sample('X6', flags=['suspected_partition']),
        sample('X7', prop_type='商业公寓'),
        sample('X8', flags=['non_residential']),
        sample('X9', detail=False),
        sample('X10', mode='unknown'),
    ]
    result = compute_rental_statistics(rows)
    reasons = {e['source_listing_id']: e['exclusion_reason'] for e in result['excluded']}
    assert reasons == {
        'X1': 'shared_rental',
        'X2': 'non_positive_value',
        'X3': 'non_positive_value',
        'X4': 'non_positive_value',
        'X5': 'non_positive_value',
        'X6': 'suspect_partition',
        'X7': 'non_residential',
        'X8': 'non_residential',
        'X9': 'detail_not_verified',
        'X10': 'unknown_rental_mode',
    }
    assert result['groups'] == []


# --- 收益估算与口径 ---

def test_estimate_yield_signed_basis():
    out = estimate_yield(90.0, 32400.0, sale_price_basis='signed',
                         sale_price_date='2026-09-01', stale=False)
    assert out['annualized_gross_yield_pct'] == pytest.approx(90.0 * 12 / 32400.0 * 100)
    assert out['rent_to_sale_ratio'] == pytest.approx(360.0)
    assert out['sale_price_basis'] == 'signed'
    assert out['sale_price_date'] == '2026-09-01'


def test_estimate_yield_listing_basis_passthrough():
    out = estimate_yield(90.0, 32400.0, sale_price_basis='listing',
                         sale_price_date=None, stale=False)
    assert out['sale_price_basis'] == 'listing'
    assert out['sale_price_date'] is None


@pytest.mark.parametrize('unit_rent, sale_price', [
    (90.0, None),
    (90.0, 0.0),
    (90.0, -1.0),
    (90.0, float('nan')),
    (90.0, float('inf')),
    (None, 32400.0),
    (0.0, 32400.0),
])
def test_estimate_yield_missing_or_invalid_inputs_yield_none(unit_rent, sale_price):
    assert estimate_yield(unit_rent, sale_price, sale_price_basis='signed',
                          sale_price_date='2026-09-01', stale=False) is None


def test_estimate_yield_requires_known_basis():
    assert estimate_yield(90.0, 32400.0, sale_price_basis=None,
                          sale_price_date=None, stale=False) is None
    assert estimate_yield(90.0, 32400.0, sale_price_basis='unknown',
                          sale_price_date=None, stale=False) is None


def test_estimate_yield_stale_returns_none():
    assert estimate_yield(90.0, 32400.0, sale_price_basis='signed',
                          sale_price_date='2026-09-01', stale=True) is None


# --- 过期判定 ---

NOW = dt.datetime(2026, 10, 12, tzinfo=dt.UTC)


def test_is_stale_after_thirty_days_utc():
    assert is_stale('2026-09-01T00:00:00+00:00', now=NOW)
    assert not is_stale('2026-09-12T00:00:00+00:00', now=NOW)
    assert not is_stale('2026-09-13T00:00:00+00:00', now=NOW)


def test_is_stale_parses_z_suffix_and_naive_utc():
    assert not is_stale('2026-10-01T00:00:00Z', now=NOW)
    assert not is_stale('2026-10-01T00:00:00', now=NOW)
    assert is_stale(None, now=NOW)
    assert is_stale('not-a-date', now=NOW)


@pytest.mark.parametrize('source,method,origin,layout,expected', [
    ('xingfuli', 'xingfuli_list_api_v1', 'community_directory', '3室1厅', 1),
    ('fang', 'xingfuli_list_api_v1', 'community_directory', '3室1厅', 0),
    ('xingfuli', 'unknown', 'community_directory', '3室1厅', 0),
    ('xingfuli', 'xingfuli_list_api_v1', None, '3室1厅', 0),
    ('xingfuli', 'xingfuli_list_api_v1', 'community_directory', None, 0),
])
def test_only_explicit_xingfuli_list_evidence_can_replace_detail(source, method, origin, layout, expected):
    from src.services.rental_reference.statistics import select_valid
    item = sample(detail=False, layout=layout)
    item.update(source=source, verification_method=method, property_type_origin=origin)
    assert len(select_valid([item])[0]) == expected

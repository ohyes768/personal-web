"""WGS84/GCJ02 控制点。期望值是离线写死的，不在运行时调用被测函数生成。

来源：scripts/convert_osm_residential.py 的 transform_lat / transform_lon
（国测局公开偏移，Krasovsky 椭球 a=6378245、ee=0.00669342162296594323）。
2026-10-28 用该公式单独预计算后写入常量。逆变换为两次迭代逼近。
"""
import math

import pytest

import scripts.convert_osm_residential as residential
import scripts.convert_osm_transit as transit
import src.services.boundary_estimate as estimate

# (wgs84_lng, wgs84_lat) -> (gcj02_lng, gcj02_lat)
FORWARD = (
    ((120.12850226078159, 30.1841956361507), (120.1332580237605, 30.18190101263762)),
    ((120.15, 30.18), (120.15470105995146, 30.17767382400918)),
    ((120.211, 30.224), (120.21553266274861, 30.221569946499475)),
    ((120.20, 30.20), (120.20455794166286, 30.19758464896)),
    ((119.99, 30.05), (119.99463880623313, 30.047504527326932)),
)

# (gcj02_lng, gcj02_lat) -> (wgs84_lng, wgs84_lat)，两次迭代
INVERSE = (
    ((120.133258, 30.181901), (120.12850226078159, 30.1841956361507)),
    ((120.155, 30.185), (120.15029919918759, 30.18732639825342)),
    ((120.216, 30.229), (120.21146782727885, 30.231430191966368)),
    ((120.0, 30.1), (119.99534314092203, 30.102478881025903)),
)

OUTSIDE = (
    (0.0, 0.0),
    (2.3522, 48.8566),
    (139.6917, 35.6895),
    (-122.4194, 37.7749),
)


def _meters(lng1, lat1, lng2, lat2) -> float:
    lat = math.radians((lat1 + lat2) / 2)
    dx = (lng1 - lng2) * 111320.0 * math.cos(lat)
    dy = (lat1 - lat2) * 110574.0
    return math.hypot(dx, dy)


def _forward_functions():
    fns = [
        estimate.wgs84_to_gcj02,
        residential.wgs84_to_gcj02,
        transit.wgs84_to_gcj02,
    ]
    try:
        from src.core import coordinates
    except ImportError:
        return fns
    fns.append(coordinates.wgs84_to_gcj02)
    return fns


def _inverse_functions():
    fns = [estimate.gcj02_to_wgs84]
    try:
        from src.core import coordinates
    except ImportError:
        return fns
    fns.append(coordinates.gcj02_to_wgs84)
    return fns


@pytest.mark.parametrize("wgs,gcj", FORWARD)
def test_forward_matches_precomputed_control(wgs, gcj):
    for fn in _forward_functions():
        got = fn(*wgs)
        assert _meters(got[0], got[1], gcj[0], gcj[1]) <= 1.0


@pytest.mark.parametrize("gcj,wgs", INVERSE)
def test_inverse_matches_precomputed_control(gcj, wgs):
    for fn in _inverse_functions():
        got = fn(*gcj)
        assert _meters(got[0], got[1], wgs[0], wgs[1]) <= 1.0


@pytest.mark.parametrize("lng,lat", OUTSIDE)
def test_outside_china_has_no_offset(lng, lat):
    for fn in _forward_functions():
        assert fn(lng, lat) == (lng, lat)
    for fn in _inverse_functions():
        assert fn(lng, lat) == (lng, lat)


def test_entry_points_agree_with_each_other():
    sample = (120.12850226078159, 30.1841956361507)
    values = [fn(*sample) for fn in _forward_functions()]
    assert len({(round(v[0], 8), round(v[1], 8)) for v in values}) == 1


def test_roundtrip_is_only_a_supplement():
    """往返不能单独证明公式正确，这里只确认残差仍小于 1 米。"""
    for wgs, _gcj in FORWARD:
        gcj = estimate.wgs84_to_gcj02(*wgs)
        back = estimate.gcj02_to_wgs84(*gcj)
        assert _meters(back[0], back[1], wgs[0], wgs[1]) <= 1.0

from src.services.community_filters import is_real_community, is_residential_community


def test_real_community_filter_rejects_road_and_known_bad_name():
    assert not is_real_community({"community_name": "江南大道", "community_id": "1"})
    assert not is_real_community({"community_name": "新街镇北塘河", "community_id": "2"})
    assert not is_real_community({"community_name": "", "community_id": "3"})


def test_real_community_filter_accepts_commercial_and_unknown_types():
    """展示与采集全量准入：商办类和类型缺失的小区都要放行，前端按物业类型筛选展示。"""
    assert is_real_community({"community_name": "逸天广场", "community_id": "10004960"})
    assert is_real_community({"community_name": "通策广场", "community_id": "shop"})
    assert is_real_community({"community_name": "类型不明小区", "community_id": "unknown"})


def test_residential_filter_accepts_housing_and_rejects_non_residential_or_unknown():
    assert is_residential_community(
        {"community_name": "春江花园", "community_id": "home"},
        {"home": {"property_type": "住宅"}},
    )
    assert is_residential_community(
        {"community_name": "江畔排屋", "community_id": "villa"},
        {"villa": {"property_type": "排屋"}},
    )
    assert not is_residential_community(
        {"community_name": "通策广场", "community_id": "shop"},
        {"shop": {"property_type": "商贸"}},
    )
    assert not is_residential_community(
        {"community_name": "类型不明小区", "community_id": "unknown"},
        {},
    )

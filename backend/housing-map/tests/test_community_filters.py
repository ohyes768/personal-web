from src.services.community_filters import is_residential_community


def test_residential_filter_rejects_road_and_known_bad_name():
    assert not is_residential_community(
        {"community_name": "江南大道", "community_id": "1"},
        {"1": {"property_type": "住宅"}},
    )
    assert not is_residential_community(
        {"community_name": "新街镇北塘河", "community_id": "2"},
        {"2": {"property_type": "住宅"}},
    )


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

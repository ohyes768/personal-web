from scripts.filter_residential_communities import split_communities
from src.services.residential_classifier import (
    RESIDENTIAL_STATE_NON_RESIDENTIAL,
    RESIDENTIAL_STATE_PENDING,
    RESIDENTIAL_STATE_RESIDENTIAL,
)


def _community(cid, name, **extra):
    base = {"community_id": cid, "community_name": name, "community_alias": name, "district": "滨江"}
    base.update(extra)
    return base


def test_split_buckets_by_state():
    communities = [
        _community("1", "住宅小区"),
        _community("2", "写字楼A"),
        _community("3", "待核实小区"),
        _community("4", "其他分类"),
    ]
    property_types = {
        "1": {"property_type": "住宅"},
        "2": {"property_type": "写字楼"},
        "3": {"property_type": "其他"},
        "4": {"property_type": "其他"},
    }
    fang_samples = {
        "3": [{"property_type": "住宅"}],
        "4": [],
    }
    result = split_communities(communities=communities, property_types=property_types, fang_samples_by_community=fang_samples)
    buckets = result["buckets"]
    assert {c["community_id"] for c in buckets[RESIDENTIAL_STATE_RESIDENTIAL]} == {"1"}
    assert {c["community_id"] for c in buckets[RESIDENTIAL_STATE_PENDING]} == {"3", "4"}
    assert {c["community_id"] for c in buckets[RESIDENTIAL_STATE_NON_RESIDENTIAL]} == {"2"}
    for entries in buckets.values():
        for entry in entries:
            assert "residential_state" in entry
            assert "residential_evidence" in entry


def test_split_preserves_evidence_in_buckets():
    communities = [_community("1", "小区A"), _community("2", "小区B")]
    property_types = {"1": {"property_type": "住宅"}, "2": {"property_type": "其他"}}
    fang_samples = {"2": [{"property_type": "住宅"}, {"property_type": "写字楼"}]}
    result = split_communities(communities=communities, property_types=property_types, fang_samples_by_community=fang_samples)
    pending = result["buckets"][RESIDENTIAL_STATE_PENDING]
    assert len(pending) == 1 and pending[0]["community_id"] == "2"
    evidence = pending[0]["residential_evidence"]
    assert evidence["tmsf"] == "其他"
    assert "住宅" in evidence["fang"] and "写字楼" in evidence["fang"]

from src.services.residential_classifier import (
    classify,
    classify_directory,
    normalize_property_type,
    RESIDENTIAL_STATE_RESIDENTIAL,
    RESIDENTIAL_STATE_NON_RESIDENTIAL,
    RESIDENTIAL_STATE_PENDING,
    RESIDENTIAL_STATE_UNKNOWN,
)


def test_normalize_handles_aliases_and_noise():
    assert normalize_property_type("住宅 别墅") == "住宅"
    assert normalize_property_type("普通住宅") == "普通住宅"
    assert normalize_property_type("写字楼 / 商铺") == "写字楼"
    assert normalize_property_type("  ") is None
    assert normalize_property_type(None) is None
    assert normalize_property_type("unknown_type_with_more_than_10") == "unknown_ty"


def test_classify_residential_via_tmsf():
    result = classify(community_id="c1", tmsf_property_type="住宅", fang_samples=[], name="小区1")
    assert result["state"] == RESIDENTIAL_STATE_RESIDENTIAL
    assert result["tmsf_property_type"] == "住宅"
    assert result["fang_property_counts"] == {}


def test_classify_non_residential_via_tmsf():
    result = classify(community_id="c2", tmsf_property_type="写字楼", fang_samples=[], name="写字楼")
    assert result["state"] == RESIDENTIAL_STATE_NON_RESIDENTIAL


def test_classify_pending_when_tmsf_other_and_no_fang():
    result = classify(community_id="c3", tmsf_property_type="其他", fang_samples=[], name="待核实")
    assert result["state"] == RESIDENTIAL_STATE_PENDING


def test_classify_residential_when_tmsf_other_and_fang_residential():
    result = classify(community_id="c4", tmsf_property_type="其他", fang_samples=[
        {"property_type": "住宅"}, {"property_type": "普通住宅"}
    ], name="4")
    assert result["state"] == RESIDENTIAL_STATE_RESIDENTIAL
    assert result["fang_property_counts"] == {"住宅": 1, "普通住宅": 1}


def test_classify_non_residential_when_tmsf_other_and_fang_non_residential():
    result = classify(community_id="c5", tmsf_property_type="其他", fang_samples=[
        {"property_type": "写字楼"}
    ], name="5")
    assert result["state"] == RESIDENTIAL_STATE_NON_RESIDENTIAL


def test_classify_unknown_when_no_signals():
    result = classify(community_id="c6", tmsf_property_type=None, fang_samples=[], name="6")
    assert result["state"] == RESIDENTIAL_STATE_UNKNOWN


def test_classify_pending_when_tmsf_other_and_fang_mixed():
    result = classify(community_id="c7", tmsf_property_type="其他", fang_samples=[
        {"property_type": "住宅"}, {"property_type": "写字楼"}
    ], name="7")
    assert result["state"] == RESIDENTIAL_STATE_PENDING


def test_classify_directory_reports_conflicts_and_summary():
    communities = [
        {"community_id": "1", "community_name": "A"},
        {"community_id": "2", "community_name": "B"},
        {"community_id": "3", "community_name": "C"},
        {"community_id": "4", "community_name": "D"},
    ]
    property_types = {
        "1": {"property_type": "住宅"},
        "2": {"property_type": "写字楼"},
        "3": {"property_type": "其他"},
        "4": {"property_type": "其他"},
    }
    fang_samples = {
        "1": [{"property_type": "写字楼"}],
        "2": [{"property_type": "住宅"}],
        "3": [{"property_type": "住宅"}, {"property_type": "写字楼"}],
        "4": [],
    }
    report = classify_directory(communities=communities, property_types=property_types, fang_samples_by_community=fang_samples)
    summary = report["summary"]
    assert summary["total"] == 4
    assert summary["residential"] == 1
    assert summary["non_residential"] == 1
    assert summary["pending"] == 2
    assert summary["unknown"] == 0
    assert len(report["conflicts"]) == 3
    kinds = {c["kind"] for c in report["conflicts"]}
    assert kinds == {
        "fang_non_residential_overrides_tmsf_residential",
        "fang_residential_overrides_tmsf_non_residential",
        "fang_mixed",
    }

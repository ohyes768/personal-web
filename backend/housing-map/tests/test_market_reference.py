import json

from src.services.market_reference import load_market_reference


VALID_SNAPSHOT = {
    "source": {
        "name": "安居客",
        "url": "https://m.anjuke.com/hz/trendency/binjiangb/",
        "captured_at": "2026-09-19",
    },
    "scope": "滨江区",
    "price_kind": "listing_reference",
    "overall": {"avg_price": 38323, "mom_percent": 0.41, "yoy_percent": 3.6},
    "subdistricts": [
        {
            "name": "西兴",
            "avg_price": 36488,
            "mom_percent": 1.8,
            "map_subdistrict": "西兴",
            "map_scope_note": "与地图街道一致",
        }
    ],
}


def test_load_market_reference_returns_a_normalized_snapshot(tmp_path):
    path = tmp_path / "market_reference.json"
    path.write_text(json.dumps(VALID_SNAPSHOT), encoding="utf-8")

    result = load_market_reference(path)

    assert result["available"] is True
    assert result["price_kind"] == "listing_reference"
    assert result["source"]["captured_at"] == "2026-09-19"
    assert result["subdistricts"][0]["name"] == "西兴"
    assert result["subdistricts"][0]["map_subdistrict"] == "西兴"


def test_load_market_reference_returns_unavailable_for_invalid_payload(tmp_path):
    path = tmp_path / "market_reference.json"
    path.write_text('{"price_kind":"deal"}', encoding="utf-8")

    assert load_market_reference(path) == {"available": False, "reason": "invalid_snapshot"}


def test_load_market_reference_returns_unavailable_for_missing_snapshot(tmp_path):
    assert load_market_reference(tmp_path / "missing.json") == {
        "available": False,
        "reason": "missing_snapshot",
    }

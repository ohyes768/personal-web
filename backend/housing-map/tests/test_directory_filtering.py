import json
from pathlib import Path

from src.services.community_directory import prepare_directory


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_prepare_skips_non_residential_when_filter_present(tmp_path):
    data = tmp_path / "data"
    _write(data / "binjiang_communities.json", [
        {"community_id": "1", "community_name": "住宅A", "community_alias": "住宅A", "district": "滨江"},
        {"community_id": "2", "community_name": "艺术园", "community_alias": "艺术园", "district": "滨江"},
    ])
    _write(data / "binjiang_residential_communities.json", [
        {"community_id": "1", "community_name": "住宅A", "community_alias": "住宅A", "district": "滨江"},
    ])
    _write(data / "binjiang_non_residential_communities.json", [
        {"community_id": "2", "community_name": "艺术园", "community_alias": "艺术园", "district": "滨江"},
    ])

    store = prepare_directory(data)
    community_ids = {c["community_id"] for c in store.communities()}
    assert community_ids == {"1"}, community_ids
    assert any(src["source_id"] == "1" for src in store.sources())


def test_prepare_uses_full_list_when_filter_missing(tmp_path):
    data = tmp_path / "data"
    _write(data / "binjiang_communities.json", [
        {"community_id": "1", "community_name": "住宅A", "community_alias": "住宅A", "district": "滨江"},
        {"community_id": "2", "community_name": "艺术园", "community_alias": "艺术园", "district": "滨江"},
    ])

    store = prepare_directory(data)
    community_ids = {c["community_id"] for c in store.communities()}
    assert community_ids == {"1", "2"}

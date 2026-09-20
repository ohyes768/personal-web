import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_merged_polygons.py"
SPEC = importlib.util.spec_from_file_location("build_merged_polygons", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)


def test_main_does_not_need_shapefile_for_unmatched_community(monkeypatch, tmp_path):
    communities_path = tmp_path / "communities.json"
    coordinates_path = tmp_path / "coordinates.json"
    osm_path = tmp_path / "osm.json"
    output_path = tmp_path / "polygons.json"
    communities_path.write_text(json.dumps([{"community_id": "1", "community_name": "无轮廓小区"}]), encoding="utf-8")
    coordinates_path.write_text(json.dumps({"1": {"longitude": 120.15, "latitude": 30.18}}), encoding="utf-8")
    osm_path.write_text(json.dumps({"features": []}), encoding="utf-8")

    monkeypatch.setattr(builder, "COMM_PATH", str(communities_path))
    monkeypatch.setattr(builder, "COORD_PATH", str(coordinates_path))
    monkeypatch.setattr(builder, "OSM_PATH", str(osm_path))
    monkeypatch.setattr(builder, "OUT_PATH", str(output_path))

    builder.main()

    assert json.loads(output_path.read_text(encoding="utf-8"))["polygons"] == {}

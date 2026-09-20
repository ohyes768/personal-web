import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_merged_polygons.py"
SPEC = importlib.util.spec_from_file_location("build_merged_polygons", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)


def replace_output_for_test(source: str, destination: str) -> None:
    """避开 Windows 临时目录中 rename/replace 的运行环境限制。"""
    source_path = Path(source)
    Path(destination).write_bytes(source_path.read_bytes())
    source_path.unlink()


def test_main_does_not_need_shapefile_for_unmatched_community(monkeypatch, tmp_path):
    communities_path = tmp_path / "communities.json"
    coordinates_path = tmp_path / "coordinates.json"
    property_types_path = tmp_path / "property_types.json"
    osm_path = tmp_path / "osm.json"
    output_path = tmp_path / "polygons.json"
    communities_path.write_text(json.dumps([{"community_id": "1", "community_name": "无轮廓小区"}]), encoding="utf-8")
    coordinates_path.write_text(json.dumps({"1": {"longitude": 120.15, "latitude": 30.18}}), encoding="utf-8")
    property_types_path.write_text(json.dumps({"1": {"property_type": "住宅"}}), encoding="utf-8")
    osm_path.write_text(json.dumps({"features": []}), encoding="utf-8")

    monkeypatch.setattr(builder, "COMM_PATH", str(communities_path))
    monkeypatch.setattr(builder, "COORD_PATH", str(coordinates_path))
    monkeypatch.setattr(builder, "PROPERTY_TYPES_PATH", str(property_types_path))
    monkeypatch.setattr(builder, "OSM_PATH", str(osm_path))
    monkeypatch.setattr(builder, "OUT_PATH", str(output_path))
    monkeypatch.setattr(builder.os, "replace", replace_output_for_test)

    builder.main()

    assert json.loads(output_path.read_text(encoding="utf-8"))["polygons"] == {}


def test_main_only_counts_residential_communities_and_logs_unmatched(monkeypatch, tmp_path, capsys):
    communities_path = tmp_path / "communities.json"
    coordinates_path = tmp_path / "coordinates.json"
    property_types_path = tmp_path / "property_types.json"
    osm_path = tmp_path / "osm.json"
    output_path = tmp_path / "polygons.json"
    communities_path.write_text(
        json.dumps(
            [
                {"community_id": "home", "community_name": "无轮廓住宅"},
                {"community_id": "office", "community_name": "办公大楼"},
                {"community_id": "road", "community_name": "江南大道"},
            ]
        ),
        encoding="utf-8",
    )
    coordinates_path.write_text(
        json.dumps(
            {
                "home": {"longitude": 120.15, "latitude": 30.18},
                "office": {"longitude": 120.16, "latitude": 30.19},
                "road": {"longitude": 120.17, "latitude": 30.20},
            }
        ),
        encoding="utf-8",
    )
    property_types_path.write_text(
        json.dumps(
            {
                "home": {"property_type": "住宅"},
                "office": {"property_type": "写字楼"},
                "road": {"property_type": "住宅"},
            }
        ),
        encoding="utf-8",
    )
    osm_path.write_text(json.dumps({"features": []}), encoding="utf-8")

    monkeypatch.setattr(builder, "COMM_PATH", str(communities_path))
    monkeypatch.setattr(builder, "COORD_PATH", str(coordinates_path))
    monkeypatch.setattr(builder, "PROPERTY_TYPES_PATH", str(property_types_path))
    monkeypatch.setattr(builder, "OSM_PATH", str(osm_path))
    monkeypatch.setattr(builder, "OUT_PATH", str(output_path))
    monkeypatch.setattr(builder.os, "replace", replace_output_for_test)

    result = builder.main()
    output = capsys.readouterr().out

    assert result == {"matched": 0, "unmatched": 1, "total": 1, "filtered": 2}
    assert "已过滤非住宅/无效条目: 2" in output
    assert "[未匹配] home 无轮廓住宅" in output


def test_default_osm_boundary_input_is_packaged_with_the_service():
    assert Path(builder.OSM_PATH).is_file()


def test_docker_image_keeps_a_seed_copy_for_existing_data_volumes():
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY data/binjiang_osm_residential.geojson ./seed-data/binjiang_osm_residential.geojson" in dockerfile
    assert "seed-data/binjiang_osm_residential.geojson" in dockerfile

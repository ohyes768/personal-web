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


def seed_directory(tmp_path):
    from src.services.community_directory import prepare_directory
    communities = [{'community_id': cid, 'community_name': name, 'district': '滨江', 'address': '滨江区测试路1号'}
                   for cid, name in [('home', '逸天广场'), ('excluded', '排除花园'), ('pending', '待审花园'), ('missing', '缺定位花园')]]
    coords = {c['community_id']: {'longitude': 120.207490, 'latitude': 30.202261,
                                'formatted_address': '滨江区测试路1号'}
              for c in communities if c['community_id'] != 'missing'}
    for name, value in {'binjiang_communities.json': communities, 'binjiang_coordinates.json': coords,
                        'property_types.json': {c['community_id']: {'property_type': '其他' if c['community_id'] == 'home' else '住宅'} for c in communities}}.items():
        (tmp_path / name).write_text(json.dumps(value), encoding='utf-8')
    store = prepare_directory(tmp_path)
    store.decide_admission('home', 'admit', revision=1, property_type='住宅')
    store.decide_admission('excluded', 'exclude', revision=1, reason='人工排除')
    store.decide_admission('pending', 'review', revision=1, reason='待核')
    return coords


def test_main_uses_effective_admitted_homes_instead_of_legacy_types(monkeypatch, tmp_path):
    coords = seed_directory(tmp_path)
    osm_path = tmp_path / 'osm.json'
    output_path = tmp_path / 'polygons.json'
    ring = [[120.207, 30.202], [120.209, 30.202], [120.209, 30.204], [120.207, 30.204], [120.207, 30.202]]
    osm_path.write_text(json.dumps({'features': [{'properties': {'name': '逸天广场'},
                                                'geometry': {'coordinates': [ring]}}]}), encoding='utf-8')
    monkeypatch.setattr(builder, 'COORD_PATH', str(tmp_path / 'binjiang_coordinates.json'))
    monkeypatch.setattr(builder, 'OSM_PATH', str(osm_path))
    monkeypatch.setattr(builder, 'OUT_PATH', str(output_path))
    monkeypatch.setattr(builder.os, 'replace', replace_output_for_test)
    assert builder.main() == {'matched': 1, 'unmatched': 0, 'total': 1, 'filtered': 3}
    assert json.loads(output_path.read_text())['polygons'] == {'home': {'source': 'osm', 'rings': [ring]}}
    assert builder.select_residential_points(tmp_path, coords)[0] == [('home', '逸天广场', 120.207490, 30.202261)]
    osm_path.write_text(json.dumps({'features': []}), encoding='utf-8')
    assert builder.main()['unmatched'] == 1
    assert json.loads(output_path.read_text())['polygons'] == {}


def test_missing_registry_preserves_existing_boundary_file(monkeypatch, tmp_path):
    import pytest
    coordinates = tmp_path / 'binjiang_coordinates.json'
    coordinates.write_text('{}', encoding='utf-8')
    output = tmp_path / 'polygons.json'
    output.write_text('{"polygons": {"old": {}}}', encoding='utf-8')
    monkeypatch.setattr(builder, 'COORD_PATH', str(coordinates))
    monkeypatch.setattr(builder, 'OUT_PATH', str(output))
    with pytest.raises(ValueError, match='缺少住宅目录数据库'):
        builder.main()
    assert json.loads(output.read_text()) == {'polygons': {'old': {}}}


def test_current_master_position_overrides_legacy_coordinate_file(tmp_path):
    from src.services.community_registry import existing_registry
    coords = seed_directory(tmp_path)
    store = existing_registry(tmp_path)
    with store.db() as db:
        row = db.execute("SELECT payload FROM communities WHERE id='home'").fetchone()
        payload = json.loads(row['payload'])
        payload.update(longitude=120.208, latitude=30.203)
        db.execute("UPDATE communities SET payload=? WHERE id='home'", (json.dumps(payload),))
    assert builder.select_residential_points(tmp_path, coords)[0] == [('home', '逸天广场', 120.208, 30.203)]


def test_default_osm_boundary_input_is_packaged_with_the_service():
    assert Path(builder.OSM_PATH).is_file()


def test_docker_image_keeps_a_seed_copy_for_existing_data_volumes():
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY data/binjiang_osm_residential.geojson ./seed-data/binjiang_osm_residential.geojson" in dockerfile
    assert "seed-data/binjiang_osm_residential.geojson" in dockerfile

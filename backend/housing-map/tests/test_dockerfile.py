from pathlib import Path


DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_startup_seeds_market_reference_when_a_persisted_volume_lacks_it():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY data/market_reference.json ./seed-data/market_reference.json" in dockerfile
    assert "[ ! -f /app/data/market_reference.json ]" in dockerfile
    assert "cp /app/seed-data/market_reference.json /app/data/" in dockerfile


def test_startup_seeds_the_building_snapshot_so_estimates_work_offline():
    """NAS 连不上 Overpass,全量建筑快照必须随镜像落到数据卷,否则生产无法生成轮廓。"""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY data/binjiang_osm_buildings_all_raw.json ./seed-data/binjiang_osm_buildings_all_raw.json" in dockerfile
    assert "[ ! -f /app/data/binjiang_osm_buildings_all_raw.json ]" in dockerfile
    assert "cp /app/seed-data/binjiang_osm_buildings_all_raw.json /app/data/" in dockerfile


def test_building_snapshot_is_tracked_by_git():
    """快照被 gitignore 排除的话,NAS 的 git pull 拿不到,镜像里就没有。"""
    import subprocess

    root = Path(__file__).resolve().parents[3]
    ignored = subprocess.run(
        ["git", "check-ignore", "backend/housing-map/data/binjiang_osm_buildings_all_raw.json"],
        cwd=root, capture_output=True, text=True)
    assert ignored.returncode != 0, "全量建筑快照仍在 .gitignore 里,NAS 构建拿不到"

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from src.main import create_app


ALBUMS = [{
    "platform": "蜻蜓FM", "album_id": "1", "title": "摇篮曲",
    "url": "https://example.invalid/album/1", "age_evidence": "蜻蜓FM年龄筛选",
    "age_confidence": "高", "sale_type": 0,
}]


def test_refresh_collects_latest_albums_and_persists_them(tmp_path: Path):
    app = create_app(
        data_dir=tmp_path / "data",
        music_dir=tmp_path / "music",
        collector=lambda: ALBUMS,
    )
    with TestClient(app) as client:
        refresh = client.post("/api/refresh")
        assert refresh.status_code == 200
        assert refresh.json()["count"] == 1
        listing = client.get("/api/albums").json()
        assert listing["albums"][0]["title"] == "摇篮曲"
        assert listing["albums"][0]["sale_type"] == 0


def test_paid_album_keeps_its_sale_type(tmp_path: Path):
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music")
    paid = [{**ALBUMS[0], "album_id": "2", "title": "会员儿歌", "sale_type": 1}]
    app.state.catalog.refresh(paid)
    with TestClient(app) as client:
        albums = {a["title"]: a for a in client.get("/api/albums").json()["albums"]}
        assert albums["会员儿歌"]["sale_type"] == 1


def test_legacy_database_gains_sale_type_column(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    with sqlite3.connect(data_dir / "kids_catalog.sqlite3") as con:
        con.executescript('''create table albums (
          id integer primary key, platform text not null, album_id text not null,
          title text not null, url text not null, age_evidence text not null,
          age_confidence text not null, last_seen text not null,
          unique(platform, album_id));''')
    app = create_app(data_dir=data_dir, music_dir=tmp_path / "music")
    app.state.catalog.refresh(ALBUMS)  # 迁移后写入不再依赖缺省列
    with TestClient(app) as client:
        assert client.get("/api/albums").json()["albums"][0]["sale_type"] == 0


def test_queue_unresolved_album_becomes_needs_authorization(tmp_path: Path):
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music")
    app.state.catalog.refresh(ALBUMS)
    with TestClient(app) as client:
        queued = client.post("/api/albums/1/download")
        assert queued.status_code == 200
        assert queued.json()["status"] == "needs_authorization"
        listing = client.get("/api/albums").json()
        assert listing["albums"][0]["download_status"] == "needs_authorization"


def test_duplicate_queue_is_idempotent(tmp_path: Path):
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music")
    app.state.catalog.refresh(ALBUMS)
    with TestClient(app) as client:
        first = client.post("/api/albums/1/download").json()
        second = client.post("/api/albums/1/download").json()
        assert first["job_id"] == second["job_id"]
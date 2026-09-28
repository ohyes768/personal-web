from pathlib import Path

from fastapi.testclient import TestClient

from src.main import create_app


ALBUMS = [{
    "platform": "蜻蜓FM", "album_id": "1", "title": "摇篮曲",
    "url": "https://example.invalid/album/1", "age_evidence": "蜻蜓FM年龄筛选",
    "age_confidence": "高",
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
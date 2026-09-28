from pathlib import Path

from fastapi.testclient import TestClient

from src.main import create_app


def test_queue_unresolved_album_becomes_needs_authorization(tmp_path: Path):
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music")
    with TestClient(app) as client:
        refresh = client.post("/api/refresh", json={"albums": [{
            "platform": "蜻蜓FM", "album_id": "1", "title": "摇篮曲",
            "url": "https://example.invalid/album/1", "age_evidence": "蜻蜓FM年龄筛选",
            "age_confidence": "高",
        }]})
        assert refresh.status_code == 200
        queued = client.post("/api/albums/1/download")
        assert queued.status_code == 200
        assert queued.json()["status"] == "needs_authorization"
        listing = client.get("/api/albums").json()
        assert listing["albums"][0]["download_status"] == "needs_authorization"


def test_duplicate_queue_is_idempotent(tmp_path: Path):
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music")
    with TestClient(app) as client:
        client.post("/api/refresh", json={"albums": [{
            "platform": "蜻蜓FM", "album_id": "1", "title": "摇篮曲",
            "url": "https://example.invalid/album/1", "age_evidence": "蜻蜓FM年龄筛选",
            "age_confidence": "高",
        }]})
        first = client.post("/api/albums/1/download").json()
        second = client.post("/api/albums/1/download").json()
        assert first["job_id"] == second["job_id"]
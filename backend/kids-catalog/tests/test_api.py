import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from src.downloader import AlbumOfflineError, DownloadReport
from src.main import create_app


ALBUMS = [{
    "platform": "蜻蜓FM", "album_id": "1", "title": "摇篮曲",
    "url": "https://example.invalid/album/1", "age_evidence": "蜻蜓FM年龄筛选",
    "age_confidence": "高", "sale_type": 0,
}]


class FakeDownloader:
    def __init__(self, report: DownloadReport | None = None):
        self.calls: list[tuple[str, str, str]] = []
        self.report = report or DownloadReport(downloaded=2)

    def download_album(self, platform, album_id, title, on_progress=None):
        self.calls.append((platform, album_id, title))
        if on_progress:
            on_progress(self.report.downloaded, self.report.downloaded + self.report.skipped)
        return self.report

    def album_size_bytes(self, platform, title):
        return 1024


def test_refresh_collects_latest_albums_and_persists_them(tmp_path: Path):
    app = create_app(
        data_dir=tmp_path / "data",
        music_dir=tmp_path / "music",
        collector=lambda: [{**ALBUMS[0], "track_count": 148}],
    )
    with TestClient(app) as client:
        refresh = client.post("/api/refresh")
        assert refresh.status_code == 200
        assert refresh.json()["count"] == 1
        listing = client.get("/api/albums").json()
        assert listing["albums"][0]["title"] == "摇篮曲"
        assert listing["albums"][0]["sale_type"] == 0
        assert listing["albums"][0]["track_count"] == 148  # 下载前就能看到曲目成本


def test_finished_download_persists_size_bytes(tmp_path: Path):
    """下载完成把专辑占用落库，前端据此显示多少 MB。"""
    downloader = FakeDownloader(DownloadReport(downloaded=2, size_bytes=2048))
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music", downloader=downloader)
    app.state.catalog.refresh(ALBUMS)
    with TestClient(app) as client:
        album_pk = client.get("/api/albums").json()["albums"][0]["id"]
        client.post(f"/api/albums/{album_pk}/download")
        deadline = time.monotonic() + 10
        listing = client.get("/api/albums").json()
        while listing["albums"][0]["download_status"] != "done" and time.monotonic() < deadline:
            time.sleep(0.05)
            listing = client.get("/api/albums").json()
        assert listing["albums"][0]["size_bytes"] == 2048


def test_legacy_done_job_backfills_size_from_disk_once(tmp_path: Path):
    """旧版本下载完的任务没有 size：列表时扫目录补算一次并持久化，不重复扫。"""
    downloader = FakeDownloader()
    downloader.album_size_bytes = lambda platform, title: 4096
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music", downloader=downloader)
    catalog = app.state.catalog
    catalog.refresh(ALBUMS)
    catalog.queue(1)
    deadline = time.monotonic() + 10
    while True:
        with catalog.db() as con:
            row = con.execute('select status from jobs').fetchone()
        if row["status"] == "done" or time.monotonic() > deadline:
            break
        time.sleep(0.05)
    with catalog.db() as con:  # 抹掉 size，模拟旧数据
        con.execute('update jobs set size_bytes=null')
    with TestClient(app) as client:
        assert client.get("/api/albums").json()["albums"][0]["size_bytes"] == 4096
    with catalog.db() as con:
        assert con.execute('select size_bytes from jobs').fetchone()[0] == 4096


def test_paid_album_keeps_its_sale_type(tmp_path: Path):
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music")
    paid = [{**ALBUMS[0], "album_id": "2", "title": "会员儿歌", "sale_type": 1}]
    app.state.catalog.refresh(paid)
    with TestClient(app) as client:
        albums = {a["title"]: a for a in client.get("/api/albums").json()["albums"]}
        assert albums["会员儿歌"]["sale_type"] == 1


def test_refresh_retires_albums_dropped_from_latest_catalog(tmp_path: Path):
    """本期榜单没有的历史专辑（含旧付费）连同下载记录清出目录，名额始终留给本期免费内容。"""
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music")
    catalog = app.state.catalog
    catalog.refresh([ALBUMS[0], {**ALBUMS[0], "album_id": "2", "title": "旧付费儿歌", "sale_type": 1}])
    catalog.queue(2)  # 排一张旧付费专辑，留下 skipped_paid 记录（不起下载线程）
    catalog.refresh([ALBUMS[0]])
    with TestClient(app) as client:
        titles = [a["title"] for a in client.get("/api/albums").json()["albums"]]
    assert titles == ["摇篮曲"]
    with catalog.db() as con:
        assert con.execute('select count(*) from jobs').fetchone()[0] == 0


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


def test_paid_album_download_is_skipped_whole_album(tmp_path: Path):
    """策略 A：付费专辑整张跳过，不启动任何下载。"""
    downloader = FakeDownloader()
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music", downloader=downloader)
    app.state.catalog.refresh([{**ALBUMS[0], "album_id": "2", "title": "会员儿歌", "sale_type": 1}])
    with TestClient(app) as client:
        album_pk = client.get("/api/albums").json()["albums"][0]["id"]
        queued = client.post(f"/api/albums/{album_pk}/download")
        assert queued.status_code == 200
        assert queued.json()["status"] == "skipped_paid"
        listing = client.get("/api/albums").json()
        assert listing["albums"][0]["download_status"] == "skipped_paid"
    assert downloader.calls == []


def test_free_album_download_runs_to_done(tmp_path: Path):
    downloader = FakeDownloader()
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music", downloader=downloader)
    app.state.catalog.refresh(ALBUMS)
    with TestClient(app) as client:
        album_pk = client.get("/api/albums").json()["albums"][0]["id"]
        queued = client.post(f"/api/albums/{album_pk}/download")
        assert queued.json()["status"] == "queued"
        deadline = time.monotonic() + 10
        listing = client.get("/api/albums").json()
        while listing["albums"][0]["download_status"] != "done" and time.monotonic() < deadline:
            time.sleep(0.05)
            listing = client.get("/api/albums").json()
        assert listing["albums"][0]["download_status"] == "done"
        assert listing["albums"][0]["downloaded_tracks"] == 2
    assert downloader.calls == [("蜻蜓FM", "1", "摇篮曲")]


def test_partial_download_reports_skipped_counts(tmp_path: Path):
    downloader = FakeDownloader(DownloadReport(downloaded=3, skipped=1))
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music", downloader=downloader)
    app.state.catalog.refresh(ALBUMS)
    with TestClient(app) as client:
        album_pk = client.get("/api/albums").json()["albums"][0]["id"]
        client.post(f"/api/albums/{album_pk}/download")
        deadline = time.monotonic() + 10
        listing = client.get("/api/albums").json()
        while listing["albums"][0]["download_status"] == "queued" and time.monotonic() < deadline:
            time.sleep(0.05)
            listing = client.get("/api/albums").json()
        assert listing["albums"][0]["download_status"] == "partial"
        assert "跳过受限 1" in listing["albums"][0]["reason"]


def test_legacy_needs_authorization_job_can_requeue(tmp_path: Path):
    """旧版占位状态的 job（NAS 数据库残留）点下载时重新排队真实下载。"""
    downloader = FakeDownloader()
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music", downloader=downloader)
    app.state.catalog.refresh(ALBUMS)
    with app.state.catalog.db() as con:
        album_pk = con.execute('select id from albums').fetchone()['id']
        con.execute("insert into jobs(album_id,status,reason,created_at,updated_at)"
                    " values(?,?,?,datetime('now'),datetime('now'))",
                    (album_pk, 'needs_authorization', '未配置已授权的媒体地址'))
    with TestClient(app) as client:
        requeued = client.post(f"/api/albums/{album_pk}/download")
        assert requeued.json()["status"] == "queued"
        deadline = time.monotonic() + 10
        listing = client.get("/api/albums").json()
        while listing["albums"][0]["download_status"] not in ("done", "partial", "failed") and time.monotonic() < deadline:
            time.sleep(0.05)
            listing = client.get("/api/albums").json()
        assert listing["albums"][0]["download_status"] == "done"
    assert downloader.calls == [("蜻蜓FM", "1", "摇篮曲")]


def test_offline_album_becomes_unavailable_and_cannot_retry(tmp_path: Path):
    """下架专辑落 unavailable 状态：页面置灰展示，重试点击幂等返回不再起线程。"""

    class OfflineDownloader:
        calls = 0

        def download_album(self, platform, album_id, title, on_progress=None):
            type(self).calls += 1
            raise AlbumOfflineError("亲，该内容因故已下架，请您谅解")

    downloader = OfflineDownloader()
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music", downloader=downloader)
    app.state.catalog.refresh(ALBUMS)
    with TestClient(app) as client:
        album_pk = client.get("/api/albums").json()["albums"][0]["id"]
        first = client.post(f"/api/albums/{album_pk}/download").json()
        deadline = time.monotonic() + 10
        listing = client.get("/api/albums").json()
        while listing["albums"][0]["download_status"] == "queued" and time.monotonic() < deadline:
            time.sleep(0.05)
            listing = client.get("/api/albums").json()
        assert listing["albums"][0]["download_status"] == "unavailable"
        assert "已下架" in listing["albums"][0]["reason"]
        again = client.post(f"/api/albums/{album_pk}/download").json()
        assert again["status"] == "unavailable"  # 不再重新排队
    assert OfflineDownloader.calls == 1


def test_duplicate_queue_is_idempotent(tmp_path: Path):
    downloader = FakeDownloader()
    app = create_app(data_dir=tmp_path / "data", music_dir=tmp_path / "music", downloader=downloader)
    app.state.catalog.refresh([{**ALBUMS[0], "sale_type": 1, "title": "会员儿歌"}])
    with TestClient(app) as client:
        album_pk = client.get("/api/albums").json()["albums"][0]["id"]
        first = client.post(f"/api/albums/{album_pk}/download").json()
        second = client.post(f"/api/albums/{album_pk}/download").json()
        assert first["job_id"] == second["job_id"]
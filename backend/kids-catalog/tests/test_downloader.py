"""下载器测试：公开接口解析、蜻蜓签名、文件名清洗、免费才下载。"""
import json
import urllib.error
from pathlib import Path

import pytest

from src.downloader import (AlbumOfflineError, Downloader, Track,
                            qingting_media_url, sanitize_filename)


def test_sanitize_filename_strips_windows_invalid_chars():
    assert sanitize_filename('宝/宝\\儿:歌*?"<>|\t') == '宝宝儿歌'
    assert sanitize_filename("宝宝巴士经典儿歌" * 10) == sanitize_filename("宝宝巴士经典儿歌" * 10)[:60]


def test_qingting_media_url_signature_snapshot():
    # 快照来自 2026-09 实测：audio.qingting.fm 放行的 HMAC-MD5 签名（密钥在蜻蜓网页 JS 公开）。
    url = qingting_media_url("326665", "14167605", now_ms=1790587000000)
    assert url == ("https://audio.qingting.fm/audiostream/redirect/326665/14167605"
                   "?access_token=&device_id=MOBILESITE&qingting_id=&t=1790587000000"
                   "&sign=b5f8b6fb9914b4956c45acb712f1eda2")


def xm_track_page(track_id: int, title: str, max_page: int = 1) -> dict:
    return {"data": {"maxPageId": max_page, "totalCount": 1, "list": [
        {"trackId": track_id, "title": title, "isPaid": False}]}}


class FakeHttp:
    """按 URL 前缀路由的假网络层。"""

    def __init__(self):
        self.json_responses: list[tuple[str, dict]] = []
        self.download_urls: list[str] = []

    def fetch_json(self, url, referer=None):
        for prefix, payload in self.json_responses:
            if url.startswith(prefix):
                return payload
        raise AssertionError(f"未预期的请求: {url}")

    def download_file(self, url, dest: Path):
        self.download_urls.append(url)
        dest.write_bytes(b"audio-bytes")


@pytest.fixture
def make_downloader(tmp_path: Path, monkeypatch):
    def make(*, platform: str, pages: list[tuple[str, dict]], throttle=0.0) -> tuple[Downloader, FakeHttp]:
        http = FakeHttp()
        http.json_responses = pages
        downloader = Downloader(tmp_path / "music", throttle_seconds=throttle)
        monkeypatch.setattr("src.downloader._fetch_json", http.fetch_json)
        monkeypatch.setattr("src.downloader._download_file", http.download_file)
        return downloader, http

    return make


def test_ximalaya_lists_tracks_across_pages(make_downloader):
    downloader, _ = make_downloader(
        platform="喜马拉雅",
        pages=[("https://mobile.ximalaya.com/mobile/v1/album/track/?albumId=4436043&pageSize=30&pageId=1",
                xm_track_page(1, "白龙马", max_page=2)),
               ("https://mobile.ximalaya.com/mobile/v1/album/track/?albumId=4436043&pageSize=30&pageId=2",
                xm_track_page(2, "采蘑菇的小姑娘"))])
    tracks = downloader.list_tracks("喜马拉雅", "4436043")
    assert [(t.track_id, t.ext) for t in tracks] == [("1", "m4a"), ("2", "m4a")]
    assert tracks[0].title == "白龙马"


def test_ximalaya_resolve_returns_none_for_restricted_track(make_downloader):
    downloader, _ = make_downloader(
        platform="喜马拉雅",
        pages=[("https://m.ximalaya.com/tracks/959103846.json",
                {"play_path_64": None, "play_path_32": None, "play_path": None})])
    track = Track("959103846", "付费曲目", "m4a")
    # 平台对未购买内容不下发地址：付费曲目天然解析不到直链。
    assert downloader.resolve_url("喜马拉雅", "4436043", track) is None


def test_qingting_resolves_signed_url_without_extra_request(make_downloader):
    downloader, _ = make_downloader(platform="蜻蜓FM", pages=[])
    track = Track("14167605", "戴口罩", "mp3")
    url = downloader.resolve_url("蜻蜓FM", "326665", track)
    assert url.startswith("https://audio.qingting.fm/audiostream/redirect/326665/14167605?")
    assert "&sign=" in url


def test_download_album_writes_numbered_files_and_reports(make_downloader):
    downloader, http = make_downloader(
        platform="喜马拉雅",
        pages=[("https://mobile.ximalaya.com/mobile/v1/album/track/?albumId=4436043&pageSize=30&pageId=1",
                xm_track_page(959103846, "白龙马")),
               ("https://m.ximalaya.com/tracks/959103846.json",
                {"play_path_64": "https://cdn.example/a.m4a", "play_path_32": None, "play_path": None})])
    progress = []
    report = downloader.download_album("喜马拉雅", "4436043", "宝宝巴士经典儿歌",
                                       on_progress=lambda done, total: progress.append((done, total)))
    assert report.downloaded == 1 and report.skipped == 0 and report.failed == 0
    album_dir = downloader.music_dir / "宝宝巴士经典儿歌"
    assert (album_dir / "001-白龙马.m4a").read_bytes() == b"audio-bytes"
    assert http.download_urls == ["https://cdn.example/a.m4a"]
    assert progress == [(1, 1)]


def test_download_album_skips_unresolvable_and_rejects(make_downloader):
    downloader, http = make_downloader(
        platform="喜马拉雅",
        pages=[("https://mobile.ximalaya.com/mobile/v1/album/track/?albumId=4436043&pageSize=30&pageId=1",
                {"data": {"maxPageId": 1, "list": [
                    {"trackId": 1, "title": "免费曲目", "isPaid": False},
                    {"trackId": 2, "title": "受限曲目", "isPaid": True}]}}),
               ("https://m.ximalaya.com/tracks/1.json",
                {"play_path_64": "https://cdn.example/free.m4a"}),
               ("https://m.ximalaya.com/tracks/2.json",
                {"play_path_64": None, "play_path_32": None, "play_path": None})])
    report = downloader.download_album("喜马拉雅", "4436043", "专辑")
    assert report.downloaded == 1 and report.skipped == 1 and report.failed == 0
    files = sorted(p.name for p in (downloader.music_dir / "专辑").iterdir())
    assert files == ["001-免费曲目.m4a"]


def test_download_album_counts_download_rejection_as_skipped(make_downloader, monkeypatch):
    def reject(url, dest):
        raise urllib.error.HTTPError(url, 401, "用户未购买", {}, None)

    downloader, _ = make_downloader(
        platform="蜻蜓FM",
        pages=[("https://i.qingting.fm/capi/v3/channel/326665",
                {"data": {"v": 1, "purchase": {"item_type": 0}}}),
               ("https://i.qingting.fm/capi/channel/326665/programs/1",
                {"data": {"total": 1, "programs": [{"id": 14167605, "title": "戴口罩", "isfree": None}]}})])
    monkeypatch.setattr("src.downloader._download_file", reject)
    report = downloader.download_album("蜻蜓FM", "326665", "三字儿歌")
    assert report.downloaded == 0 and report.skipped == 1 and report.failed == 0


def test_ximalaya_offline_album_error_is_surfaced(make_downloader):
    downloader, _ = make_downloader(
        platform="喜马拉雅",
        pages=[("https://mobile.ximalaya.com/mobile/v1/album/track/",
                {"ret": 924, "msg": "亲，该内容因故已下架，请您谅解"})])
    with pytest.raises(AlbumOfflineError, match="已下架"):
        downloader.list_tracks("喜马拉雅", "12263592")


def test_download_album_existing_file_is_resumed_not_redownloaded(make_downloader):
    downloader, http = make_downloader(
        platform="喜马拉雅",
        pages=[("https://mobile.ximalaya.com/mobile/v1/album/track/?albumId=4436043&pageSize=30&pageId=1",
                xm_track_page(959103846, "白龙马")),
               ("https://m.ximalaya.com/tracks/959103846.json",
                {"play_path_64": "https://cdn.example/a.m4a"})])
    existing = downloader.music_dir / "重跑专辑" / "001-白龙马.m4a"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"already-here")
    report = downloader.download_album("喜马拉雅", "4436043", "重跑专辑")
    assert report.downloaded == 1
    assert http.download_urls == []  # 已存在的文件不重复下载
    assert existing.read_bytes() == b"already-here"

"""下载器测试：公开接口解析、蜻蜓签名、文件名清洗、免费才下载。"""
import json
import urllib.error
from pathlib import Path

import pytest

from src.downloader import (AlbumOfflineError, Downloader, DownloadReport, SkipReason,
                            Track, NETEASE_ALBUM, NETEASE_PLAYLIST,
                            qingting_media_url, sanitize_filename, track_total)


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


def xm_single_payload(track_id: int, title: str, max_page: int = 1) -> dict:
    """旧接口 album/single 的响应形状（2026-10-24 实测）。"""
    return {"ret": 0, "data": {"album": {"title": "听，小蜗牛艾玛"}, "tracks": {
        "list": [{"trackId": track_id, "title": title, "isPaid": False}],
        "pageId": 1, "pageSize": 30, "totalCount": 1, "maxPageId": max_page}}}


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

    def download_file(self, url, dest: Path, referer=None):
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


def test_ximalaya_lists_tracks_via_single_api_fallback(make_downloader):
    """新版接口下架(ret=924)、旧接口仍在服务（2026-10-24 实测）：下载列表自动回退旧接口。"""
    downloader, _ = make_downloader(
        platform="喜马拉雅",
        pages=[("https://mobile.ximalaya.com/mobile/v1/album/track/?albumId=16350309&pageSize=30&pageId=1",
                {"ret": 924, "msg": "亲，该内容因故已下架，请您谅解"}),
               ("https://mobile.ximalaya.com/mobile/v1/album/single?albumId=16350309&pageSize=30&pageId=1",
                xm_single_payload(98082355, "听，小蜗牛艾玛——完整版"))])
    tracks = downloader.list_tracks("喜马拉雅", "16350309")
    assert [(t.track_id, t.title, t.ext) for t in tracks] == [
        ("98082355", "听，小蜗牛艾玛——完整版", "m4a")]


def test_ximalaya_offline_album_error_is_surfaced(make_downloader):
    """新旧接口都报 924 才抛 AlbumOfflineError。"""
    downloader, _ = make_downloader(
        platform="喜马拉雅",
        pages=[("https://mobile.ximalaya.com/mobile/v1/album/track/?albumId=12263592&pageSize=30&pageId=1",
                {"ret": 924, "msg": "亲，该内容因故已下架，请您谅解"}),
               ("https://mobile.ximalaya.com/mobile/v1/album/single?albumId=12263592&pageSize=30&pageId=1",
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


def test_track_total_reads_platform_totals(make_downloader):
    """下载前成本提示的数据源：喜马拉雅 totalCount、蜻蜓 programs total，一页即可。"""
    make_downloader(
        platform="喜马拉雅",
        pages=[("https://mobile.ximalaya.com/mobile/v1/album/track/?albumId=4436043&pageSize=1&pageId=1",
                {"data": {"maxPageId": 5, "totalCount": 148, "list": []}}),
               ("https://i.qingting.fm/capi/v3/channel/326665", {"data": {"v": 9}}),
               ("https://i.qingting.fm/capi/channel/326665/programs/9", {"data": {"total": 60, "programs": []}})])
    assert track_total("喜马拉雅", "4436043") == 148
    assert track_total("蜻蜓FM", "326665") == 60
    assert track_total("未知平台", "1") is None


def test_track_total_missing_field_returns_none(make_downloader):
    make_downloader(
        platform="喜马拉雅",
        pages=[("https://mobile.ximalaya.com/mobile/v1/album/track/",
                {"data": {"maxPageId": 1, "list": []}})])
    assert track_total("喜马拉雅", "4436043") is None


def test_download_album_reports_directory_size(make_downloader):
    downloader, _ = make_downloader(
        platform="喜马拉雅",
        pages=[("https://mobile.ximalaya.com/mobile/v1/album/track/?albumId=4436043&pageSize=30&pageId=1",
                xm_track_page(959103846, "白龙马")),
               ("https://m.ximalaya.com/tracks/959103846.json",
                {"play_path_64": "https://cdn.example/a.m4a"})])
    report = downloader.download_album("喜马拉雅", "4436043", "大小专辑")
    assert report.size_bytes == len(b"audio-bytes")


def test_album_size_bytes_missing_directory_returns_none(tmp_path: Path):
    downloader = Downloader(tmp_path / "music")
    assert downloader.album_size_bytes("喜马拉雅", "从未下载") is None


# --- 网易云音乐（2026-11-02 实测接口，见 task research/findings.md）---


def netease_playlist_payload(track_ids):
    return {"code": 200, "playlist": {"name": "歌单", "trackCount": len(track_ids),
                                      "trackIds": [{"id": i} for i in track_ids]}}


def netease_song_detail(songs):
    return {"code": 200, "songs": songs}


def netease_player(data):
    return {"code": 200, "data": data}


def test_netease_playlist_lists_tracks_in_order(make_downloader):
    """歌单 trackIds 给全量 ID，标题分批取；顺序按 trackIds 保持。"""
    downloader, _ = make_downloader(
        platform=NETEASE_PLAYLIST,
        pages=[("https://music.163.com/api/v3/playlist/detail?id=13907752641",
                netease_playlist_payload([11, 22])),
               ("https://music.163.com/api/song/detail/?ids=",
                netease_song_detail([{"id": 11, "name": "小星星"}, {"id": 22, "name": "摇篮曲"}]))])
    tracks = downloader.list_tracks(NETEASE_PLAYLIST, "13907752641")
    assert [(t.track_id, t.title, t.ext) for t in tracks] == [
        ("11", "小星星", "mp3"), ("22", "摇篮曲", "mp3")]


def test_netease_album_lists_tracks_from_songs(make_downloader):
    """专辑 songs 一次全量返回，不需要二次请求标题。"""
    downloader, http = make_downloader(
        platform=NETEASE_ALBUM,
        pages=[("https://music.163.com/api/v1/album/34720827",
                {"code": 200, "album": {"name": "周杰伦的床边故事", "size": 2},
                 "songs": [{"id": 415792916, "name": "床边故事"},
                           {"id": 418602084, "name": "说走就走"}]})])
    tracks = downloader.list_tracks(NETEASE_ALBUM, "34720827")
    assert [(t.track_id, t.title) for t in tracks] == [
        ("415792916", "床边故事"), ("418602084", "说走就走")]
    # 只有一次请求：album 的 songs 已带标题
    assert len(http.json_responses) == 1


def test_netease_batch_urls_aligns_by_id_not_by_order(make_downloader):
    """player/url 的返回顺序不保证与请求一致（2026-11-02 实测踩过的坑）。

    故意让响应乱序，若按位置匹配会把直链安到错误的曲目上。
    """
    downloader, _ = make_downloader(
        platform=NETEASE_PLAYLIST,
        pages=[("https://music.163.com/api/song/enhance/player/url",
                netease_player([{"id": 22, "url": "https://cdn.example/b.mp3", "code": 200},
                                {"id": 11, "url": "https://cdn.example/a.mp3", "code": 200}]))])
    urls, reasons = downloader._netease_batch_urls(["11", "22"])
    assert urls == {"11": "https://cdn.example/a.mp3", "22": "https://cdn.example/b.mp3"}
    assert reasons == {}


def test_netease_vip_and_missing_source_report_reasons(make_downloader):
    """code=-110 是 VIP 未放行；无 url 是平台无音源；两者都逐条跳过并说明原因。"""
    downloader, _ = make_downloader(
        platform=NETEASE_PLAYLIST,
        pages=[("https://music.163.com/api/song/enhance/player/url",
                netease_player([{"id": 11, "url": None, "code": -110},
                                {"id": 22, "url": None, "code": 404}]))])
    urls, reasons = downloader._netease_batch_urls(["11", "22"])
    assert urls == {}
    assert reasons["11"] == "VIP 付费曲目，平台未放行"
    assert reasons["22"] == "平台无可用音源"


def test_netease_track_missing_from_response_is_marked_no_source(make_downloader):
    """接口没返回的曲目同样没有可用音源，不能当作成功。"""
    downloader, _ = make_downloader(
        platform=NETEASE_PLAYLIST,
        pages=[("https://music.163.com/api/song/enhance/player/url",
                netease_player([{"id": 11, "url": "https://cdn.example/a.mp3", "code": 200}]))])
    urls, reasons = downloader._netease_batch_urls(["11", "22"])
    assert list(urls) == ["11"]
    assert reasons == {"22": "平台无可用音源"}


def test_netease_download_album_skips_vip_with_reason(make_downloader):
    """免费曲落盘、VIP 曲跳过且带原因；文件名为 NNN-标题.mp3。"""
    downloader, http = make_downloader(
        platform=NETEASE_PLAYLIST,
        pages=[("https://music.163.com/api/v3/playlist/detail?id=13907752641",
                netease_playlist_payload([11, 22])),
               ("https://music.163.com/api/song/detail/?ids=",
                netease_song_detail([{"id": 11, "name": "小星星"}, {"id": 22, "name": "付费曲"}])),
               ("https://music.163.com/api/song/enhance/player/url",
                netease_player([{"id": 11, "url": "https://cdn.example/a.mp3", "code": 200},
                                {"id": 22, "url": None, "code": -110}]))])
    report = downloader.download_album(NETEASE_PLAYLIST, "13907752641", "婴儿哄睡必听")
    assert report.downloaded == 1 and report.skipped == 1 and report.failed == 0
    files = sorted(p.name for p in (downloader.music_dir / "婴儿哄睡必听").iterdir())
    assert files == ["001-小星星.mp3"]
    assert report.skip_reasons == (SkipReason("付费曲", "VIP 付费曲目，平台未放行"),)


def test_netease_download_failure_is_not_counted_as_skipped(make_downloader, monkeypatch):
    """网络故障如实记为 failed，不能当成跳过或成功。"""
    downloader, _ = make_downloader(
        platform=NETEASE_PLAYLIST,
        pages=[("https://music.163.com/api/v3/playlist/detail?id=1",
                netease_playlist_payload([11])),
               ("https://music.163.com/api/song/detail/?ids=",
                netease_song_detail([{"id": 11, "name": "小星星"}])),
               ("https://music.163.com/api/song/enhance/player/url",
                netease_player([{"id": 11, "url": "https://cdn.example/a.mp3", "code": 200}]))])

    def boom(url, dest, referer=None):
        raise OSError("connection reset")

    monkeypatch.setattr("src.downloader._download_file", boom)
    report = downloader.download_album(NETEASE_PLAYLIST, "1", "歌单")
    assert report.downloaded == 0 and report.skipped == 0 and report.failed == 1


def test_netease_http_403_counts_as_skipped_not_failed(make_downloader, monkeypatch):
    """403 = 直链失效/音源被撤，属不可下载而非网络故障。"""
    downloader, _ = make_downloader(
        platform=NETEASE_PLAYLIST,
        pages=[("https://music.163.com/api/v3/playlist/detail?id=1",
                netease_playlist_payload([11])),
               ("https://music.163.com/api/song/detail/?ids=",
                netease_song_detail([{"id": 11, "name": "小星星"}])),
               ("https://music.163.com/api/song/enhance/player/url",
                netease_player([{"id": 11, "url": "https://cdn.example/a.mp3", "code": 200}]))])

    def reject(url, dest, referer=None):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)

    monkeypatch.setattr("src.downloader._download_file", reject)
    report = downloader.download_album(NETEASE_PLAYLIST, "1", "歌单")
    assert report.downloaded == 0 and report.skipped == 1 and report.failed == 0
    assert report.skip_reasons == (SkipReason("小星星", "音源不可用"),)


def test_netease_download_resumes_existing_files(make_downloader):
    """已存在的同名文件视为已完成，不重复下载（断点续传）。"""
    downloader, http = make_downloader(
        platform=NETEASE_PLAYLIST,
        pages=[("https://music.163.com/api/v3/playlist/detail?id=1",
                netease_playlist_payload([11])),
               ("https://music.163.com/api/song/detail/?ids=",
                netease_song_detail([{"id": 11, "name": "小星星"}])),
               ("https://music.163.com/api/song/enhance/player/url",
                netease_player([{"id": 11, "url": "https://cdn.example/a.mp3", "code": 200}]))])
    album_dir = downloader.music_dir / "歌单"
    album_dir.mkdir(parents=True)
    (album_dir / "001-小星星.mp3").write_bytes(b"old")
    report = downloader.download_album(NETEASE_PLAYLIST, "1", "歌单")
    assert report.downloaded == 1
    assert http.download_urls == []


def test_skip_summary_groups_reasons_and_lists_samples():
    report = DownloadReport(skipped=3, skip_reasons=(
        SkipReason("付费曲甲", "VIP 付费曲目，平台未放行"),
        SkipReason("付费曲乙", "VIP 付费曲目，平台未放行"),
        SkipReason("无源曲", "平台无可用音源")))
    summary = report.skip_summary()
    assert "VIP 付费曲目，平台未放行 2 首" in summary
    assert "平台无可用音源 1 首" in summary
    assert "《付费曲甲》" in summary


def test_skip_summary_is_empty_without_reasons():
    assert DownloadReport().skip_summary() == ""


def test_netease_resolve_url_returns_direct_link(make_downloader):
    """resolve_url 对网易云也要能用（逐曲调用时同样返回直链）。"""
    downloader, _ = make_downloader(
        platform=NETEASE_PLAYLIST,
        pages=[("https://music.163.com/api/song/enhance/player/url",
                netease_player([{"id": 11, "url": "https://cdn.example/a.mp3", "code": 200}]))])
    assert downloader.resolve_url(NETEASE_PLAYLIST, "1", Track("11", "小星星", "mp3")) \
        == "https://cdn.example/a.mp3"


def test_netease_resolve_url_returns_none_for_vip(make_downloader):
    downloader, _ = make_downloader(
        platform=NETEASE_PLAYLIST,
        pages=[("https://music.163.com/api/song/enhance/player/url",
                netease_player([{"id": 11, "url": None, "code": -110}]))])
    assert downloader.resolve_url(NETEASE_PLAYLIST, "1", Track("11", "付费曲", "mp3")) is None

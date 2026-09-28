"""免费专辑下载器：喜马拉雅/蜻蜓公开接口解析直链并落盘到 music_dir。

只下载免费内容（策略 A）：付费专辑由调用方整张跳过；免费专辑内的受限曲目
平台不下发地址（喜马拉雅 play_path=None、蜻蜓 401 未购买），逐条跳过。

接口来源（2026-09 实测，与 RSSHub/musicdl 现役实现一致，均免登录）：
- 喜马拉雅曲目列表 mobile.ximalaya.com/mobile/v1/album/track/（maxPageId 翻页）
- 喜马拉雅直链 m.ximalaya.com/tracks/{id}.json → play_path_64（m4a）
- 蜻蜓专辑/曲目 i.qingting.fm/capi/v3/channel/{id} + .../programs/{v}（一页全量）
- 蜻蜓直链 audio.qingting.fm/audiostream/redirect/... + HMAC-MD5 签名（密钥在蜻蜓网页 JS 公开）
"""
import hashlib
import hmac
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
XM_TRACKS_URL = "https://mobile.ximalaya.com/mobile/v1/album/track/"
XM_TRACK_URL = "https://m.ximalaya.com/tracks/{track_id}.json"
QT_CHANNEL_URL = "https://i.qingting.fm/capi/v3/channel/{channel_id}"
QT_PROGRAMS_URL = "https://i.qingting.fm/capi/channel/{channel_id}/programs/{version}"
QT_REFERER = "https://www.qingting.fm/"
# 蜻蜓播放地址的客户端签名密钥（网页 JS 明文公开，非破解）。
QT_HMAC_KEY = b"fpMn12&38f_2e"
PAGE_SIZE = 30
# 翻页硬上限：防御接口异常返回导致的无限循环。
MAX_PAGES = 100
INVALID_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t]')
MAX_NAME_LENGTH = 60
PLATFORM_DIRS = (("蜻蜓", "蜻蜓FM"), ("喜马拉雅", "喜马拉雅"))


@dataclass(frozen=True)
class Track:
    track_id: str
    title: str
    ext: str  # 喜马拉雅 m4a / 蜻蜓 mp3


@dataclass(frozen=True)
class DownloadReport:
    downloaded: int = 0
    skipped: int = 0  # 平台未放行（付费/受限）曲目
    failed: int = 0   # 网络或写盘失败


def sanitize_filename(name: str) -> str:
    return INVALID_FILENAME.sub("", name)[:MAX_NAME_LENGTH].rstrip(". ")


def qingting_media_url(channel_id: str, media_id: str, now_ms: int | None = None) -> str:
    """构造带 HMAC-MD5 签名的播放直链（实时构造即可，地址约 1 天有效）。"""
    path = (f"/audiostream/redirect/{channel_id}/{media_id}"
            f"?access_token=&device_id=MOBILESITE&qingting_id=&t={now_ms or int(time.time() * 1000)}")
    sign = hmac.new(QT_HMAC_KEY, path.encode(), hashlib.md5).hexdigest()
    return f"https://audio.qingting.fm{path}&sign={sign}"


def _fetch_json(url: str, referer: str | None = None) -> dict:
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _download_file(url: str, dest: Path) -> None:
    """流式下载到 .part 临时文件后原子改名，避免半截文件被当作已完成。"""
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": QT_REFERER})
    partial = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as out:
        while chunk := response.read(64 * 1024):
            out.write(chunk)
    partial.replace(dest)


class Downloader:
    def __init__(self, music_dir: Path, throttle_seconds: float = 1.0, page_pause_seconds: float = 0.3):
        self.music_dir = Path(music_dir)
        self.throttle_seconds = throttle_seconds
        self.page_pause_seconds = page_pause_seconds

    def list_tracks(self, platform: str, album_id: str) -> list[Track]:
        if "喜马拉雅" in platform:
            return self._list_ximalaya(album_id)
        if "蜻蜓" in platform:
            return self._list_qingting(album_id)
        raise ValueError(f"不支持的下载来源: {platform}")

    def resolve_url(self, platform: str, album_id: str, track: Track) -> str | None:
        """返回可直接下载的地址；平台未放行（付费/受限）时返回 None。"""
        if "喜马拉雅" in platform:
            data = _fetch_json(XM_TRACK_URL.format(track_id=track.track_id),
                               referer=f"https://m.ximalaya.com/sound/{track.track_id}")
            url = data.get("play_path_64") or data.get("play_path_32") or data.get("play_path")
            return url if isinstance(url, str) and url.startswith("http") else None
        if "蜻蜓" in platform:
            return qingting_media_url(album_id, track.track_id)
        raise ValueError(f"不支持的下载来源: {platform}")

    def download_album(self, platform: str, album_id: str, album_title: str,
                       on_progress=None) -> DownloadReport:
        """串行下载整张专辑到 music_dir/<平台>/<专辑>/，返回结果统计。

        已存在的同名文件视为已完成，不重复下载（简单断点续传）。
        """
        tracks = self.list_tracks(platform, album_id)
        album_dir = self.album_dir(platform, album_title)
        album_dir.mkdir(parents=True, exist_ok=True)
        report = DownloadReport()
        for index, track in enumerate(tracks, start=1):
            report = self._download_one(platform, album_id, track, index, album_dir, report)
            if on_progress:
                on_progress(index, len(tracks))
            time.sleep(self.throttle_seconds)
        return report

    def album_dir(self, platform: str, album_title: str) -> Path:
        directory = next((target for keyword, target in PLATFORM_DIRS if keyword in platform), platform)
        return self.music_dir / directory / sanitize_filename(album_title)

    def _download_one(self, platform: str, album_id: str, track: Track, index: int,
                      album_dir: Path, report: DownloadReport) -> DownloadReport:
        dest = album_dir / f"{index:03d}-{sanitize_filename(track.title)}.{track.ext}"
        try:
            if dest.exists():
                return replace(report, downloaded=report.downloaded + 1)
            url = self.resolve_url(platform, album_id, track)
            if not url:
                return replace(report, skipped=report.skipped + 1)
            _download_file(url, dest)
            return replace(report, downloaded=report.downloaded + 1)
        except urllib.error.HTTPError as exc:
            # 401/403 = 平台判定未购买/未放行，属受限内容而非故障。
            if exc.code in (401, 403):
                return replace(report, skipped=report.skipped + 1)
            return replace(report, failed=report.failed + 1)
        except Exception:
            return replace(report, failed=report.failed + 1)

    def _list_ximalaya(self, album_id: str) -> list[Track]:
        tracks: list[Track] = []
        page = 1
        while page <= MAX_PAGES:
            payload = _fetch_json(f"{XM_TRACKS_URL}?albumId={album_id}&pageSize={PAGE_SIZE}&pageId={page}",
                                  referer=f"https://www.ximalaya.com/album/{album_id}")
            if "data" not in payload:
                # 实测下架专辑返回 {"ret": 924, "msg": "该内容因故已下架"}，须透出真实原因。
                raise RuntimeError(payload.get("msg") or f"喜马拉雅曲目接口异常: ret={payload.get('ret')}")
            data = payload["data"]
            for item in data.get("list", []):
                tracks.append(Track(str(item["trackId"]), str(item["title"]), "m4a"))
            if page >= (data.get("maxPageId") or 1):
                return tracks
            page += 1
            time.sleep(self.page_pause_seconds)
        return tracks

    def _list_qingting(self, channel_id: str) -> list[Track]:
        version = _fetch_json(QT_CHANNEL_URL.format(channel_id=channel_id),
                              referer=QT_REFERER)["data"]["v"]
        tracks: list[Track] = []
        page = 1
        while page <= MAX_PAGES:
            data = _fetch_json(f"{QT_PROGRAMS_URL.format(channel_id=channel_id, version=version)}"
                               f"?curpage={page}&pagesize=100&order=asc", referer=QT_REFERER).get("data", {})
            programs = data.get("programs", [])
            tracks.extend(Track(str(p["id"]), str(p["title"]), "mp3") for p in programs)
            if not programs or len(tracks) >= (data.get("total") or len(tracks)):
                return tracks
            page += 1
            time.sleep(self.page_pause_seconds)
        return tracks

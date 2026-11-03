"""免费专辑下载器：喜马拉雅/蜻蜓公开接口解析直链并落盘到 music_dir。

只下载免费内容（策略 A）：付费专辑由调用方整张跳过；免费专辑内的受限曲目
平台不下发地址（喜马拉雅 play_path=None、蜻蜓 401 未购买），逐条跳过。

接口来源（2026-09 实测，与 RSSHub/musicdl 现役实现一致，均免登录）：
- 喜马拉雅曲目列表 mobile.ximalaya.com/mobile/v1/album/track/（maxPageId 翻页；
  ret=924 时回退旧接口 mobile/v1/album/single，实测一批"下架"专辑旧接口仍在服务）
- 喜马拉雅直链 m.ximalaya.com/tracks/{id}.json → play_path_64（m4a）
- 蜻蜓专辑/曲目 i.qingting.fm/capi/v3/channel/{id} + .../programs/{v}（一页全量）
- 蜻蜓直链 audio.qingting.fm/audiostream/redirect/... + HMAC-MD5 签名（密钥在蜻蜓网页 JS 公开）
- 网易云 2026-11-02 实测（全部免登录）：
  歌单 music.163.com/api/v3/playlist/detail?id= → playlist.trackIds 全量曲目 ID
  专辑 music.163.com/api/v1/album/{id} → songs 一次全量（/api/album/{id} 恒返回空 songs）
  曲目 music.163.com/api/song/detail/?ids=[...] → id/name/fee
  直链 music.163.com/api/song/enhance/player/url?ids=[...]&br=128000 → data[].url
  接口分批上限 200：song/detail 与 player/url 传更多只回前 200 条。
  ⚠️ player/url 的返回顺序不保证与请求顺序一致，必须按 id 建字典对齐。
"""
import hashlib
import hmac
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NamedTuple

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
XM_TRACKS_URL = "https://mobile.ximalaya.com/mobile/v1/album/track/"
XM_SINGLE_URL = "https://mobile.ximalaya.com/mobile/v1/album/single"
XM_TRACK_URL = "https://m.ximalaya.com/tracks/{track_id}.json"
QT_CHANNEL_URL = "https://i.qingting.fm/capi/v3/channel/{channel_id}"
QT_PROGRAMS_URL = "https://i.qingting.fm/capi/channel/{channel_id}/programs/{version}"
QT_REFERER = "https://www.qingting.fm/"
# 网易云音乐：歌单与专辑是两个 ID 空间（实测 id=2884035 既是歌单又是专辑），
# 故用两个 platform 名区分，让 albums 表的 (platform, album_id) 天然唯一。
NETEASE_PLAYLIST = "网易云歌单"
NETEASE_ALBUM = "网易云专辑"
NETEASE_REFERER = "https://music.163.com/"
NETEASE_PLAYLIST_URL = "https://music.163.com/api/v3/playlist/detail?id={playlist_id}"
NETEASE_ALBUM_URL = "https://music.163.com/api/v1/album/{album_id}"
NETEASE_SONG_DETAIL_URL = "https://music.163.com/api/song/detail/?ids={ids}"
NETEASE_PLAYER_URL = "https://music.163.com/api/song/enhance/player/url?ids={ids}&br=128000"
# 网易云接口单批上限（实测传 300 只回 201 条，传 965 回 0 条）。
NETEASE_BATCH_SIZE = 200
# 蜻蜓播放地址的客户端签名密钥（网页 JS 明文公开，非破解）。
QT_HMAC_KEY = b"fpMn12&38f_2e"
PAGE_SIZE = 30
# 翻页硬上限：防御接口异常返回导致的无限循环。
MAX_PAGES = 100
INVALID_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t]')
MAX_NAME_LENGTH = 60


@dataclass(frozen=True)
class Track:
    track_id: str
    title: str
    ext: str  # 喜马拉雅 m4a / 蜻蜓 mp3


class SkipReason(NamedTuple):
    """某首曲目被跳过的原因（平台未放行 / 无音源）。"""
    title: str
    reason: str


@dataclass(frozen=True)
class DownloadReport:
    downloaded: int = 0
    skipped: int = 0  # 平台未放行（付费/受限）曲目
    failed: int = 0   # 网络或写盘失败
    size_bytes: int | None = None  # 专辑目录占用；未落盘/已清理时 None
    # 逐条跳过原因；只有网易云会填充。
    # 用 NamedTuple 而非 dict：DownloadReport 是 frozen dataclass，保持可哈希。
    skip_reasons: tuple[SkipReason, ...] = ()

    def skip_summary(self, max_items: int = 5) -> str:
        """把逐条跳过原因汇总成一句用户可读的说明。

        按原因分组计数，并列出前几条具体曲目，避免上百首时刷屏。
        """
        if not self.skip_reasons:
            return ""
        counts: dict[str, int] = {}
        for item in self.skip_reasons:
            counts[item.reason] = counts.get(item.reason, 0) + 1
        breakdown = "、".join(f"{reason} {count} 首" for reason, count in counts.items())
        samples = "；".join(f"《{item.title}》{item.reason}"
                            for item in self.skip_reasons[:max_items])
        text = f"{breakdown}（{samples}"
        if len(self.skip_reasons) > max_items:
            text += f" 等 {len(self.skip_reasons)} 首"
        return text + "）"


class AlbumOfflineError(RuntimeError):
    """专辑已被平台下架（如喜马拉雅 ret=924），重试也无法下载。"""


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


XM_OFFLINE_RET = 924  # 实测下架专辑 mobile 接口返回 {"ret": 924, "msg": "该内容因故已下架"}


def ximalaya_album_available(album_id: str) -> bool:
    """预检专辑在移动端接口是否仍可访问；网页热门榜会残留已下架专辑。"""
    payload = _fetch_json(f"{XM_TRACKS_URL}?albumId={album_id}&pageSize=1&pageId=1")
    return payload.get("ret") != XM_OFFLINE_RET


def xm_tracks_page(fetch, album_id: str, page: int, referer: str | None = None) -> dict:
    """取一页曲目列表；新版接口 ret=924 时回退旧接口 single 并归一化其响应。

    实测（2026-10-24）平台把一批专辑从新版接口下架（ret=924），旧接口
    mobile/v1/album/single 仍在服务：data 为 {album:{...}, tracks:{list,maxPageId,
    totalCount}}，曲目项字段（trackId/title/isPaid）与新版一致。归一化时把专辑名
    注入每条曲目项的 albumTitle，调用方按新版响应形状消费；两个接口都不可用时
    原样返回 924 payload，由调用方决定报错方式。
    """
    payload = fetch(f"{XM_TRACKS_URL}?albumId={album_id}&pageSize={PAGE_SIZE}&pageId={page}", referer=referer)
    if payload.get("ret") != XM_OFFLINE_RET:
        return payload
    single = fetch(f"{XM_SINGLE_URL}?albumId={album_id}&pageSize={PAGE_SIZE}&pageId={page}", referer=referer)
    data = single.get("data") or {}
    tracks = data.get("tracks") or {}
    if not tracks.get("list"):
        return payload
    album = data.get("album") or {}
    items = [dict(item, albumTitle=album.get("title")) for item in tracks["list"]]
    return {"ret": single.get("ret"), "msg": single.get("msg"),
            "data": {"list": items, "totalCount": tracks.get("totalCount"),
                     "maxPageId": tracks.get("maxPageId"),
                     "pageId": tracks.get("pageId"), "pageSize": tracks.get("pageSize")}}


def track_total(platform: str, album_id: str) -> int | None:
    """下载前曲目总数（成本提示）：喜马拉雅读 totalCount，蜻蜓读 programs total；取不到返回 None。"""
    if "喜马拉雅" in platform:
        payload = _fetch_json(f"{XM_TRACKS_URL}?albumId={album_id}&pageSize=1&pageId=1")
        total = (payload.get("data") or {}).get("totalCount")
        return total if isinstance(total, int) else None
    if "蜻蜓" in platform:
        data = _fetch_json(f"{QT_PROGRAMS_URL.format(channel_id=album_id, version=_qingting_version(album_id))}"
                           f"?curpage=1&pagesize=1&order=asc", referer=QT_REFERER).get("data", {})
        total = data.get("total")
        return total if isinstance(total, int) else None
    return None


def _qingting_version(channel_id: str) -> str:
    return _fetch_json(QT_CHANNEL_URL.format(channel_id=channel_id),
                       referer=QT_REFERER)["data"]["v"]


def _download_file(url: str, dest: Path, referer: str | None = QT_REFERER) -> None:
    """流式下载到 .part 临时文件后原子改名，避免半截文件被当作已完成。"""
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
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
        if platform == NETEASE_PLAYLIST:
            return self._list_netease_playlist(album_id)
        if platform == NETEASE_ALBUM:
            return self._list_netease_album(album_id)
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
        if platform in (NETEASE_PLAYLIST, NETEASE_ALBUM):
            urls, _ = self._netease_batch_urls([track.track_id])
            return urls.get(track.track_id)
        raise ValueError(f"不支持的下载来源: {platform}")

    def download_album(self, platform: str, album_id: str, album_title: str,
                       on_progress=None) -> DownloadReport:
        """串行下载整张专辑到 music_dir/<平台>/<专辑>/，返回结果统计。

        已存在的同名文件视为已完成，不重复下载（简单断点续传）。
        """
        if platform in (NETEASE_PLAYLIST, NETEASE_ALBUM):
            return self._download_netease(platform, album_id, album_title, on_progress)
        tracks = self.list_tracks(platform, album_id)
        album_dir = self.album_dir(platform, album_title)
        album_dir.mkdir(parents=True, exist_ok=True)
        report = DownloadReport()
        for index, track in enumerate(tracks, start=1):
            report = self._download_one(platform, album_id, track, index, album_dir, report)
            if on_progress:
                on_progress(index, len(tracks))
            time.sleep(self.throttle_seconds)
        return replace(report, size_bytes=self.album_size_bytes(platform, album_title))

    def album_dir(self, platform: str, album_title: str) -> Path:
        # xiaomusic 按「目录=专辑」扫曲库，专辑直接平铺在 music 根目录下（不按平台分层）。
        return self.music_dir / sanitize_filename(album_title)

    def album_size_bytes(self, platform: str, album_title: str) -> int | None:
        """专辑目录占用字节数（含未清掉的 .part 残留，如实反映磁盘占用）；目录不存在返回 None。"""
        album_dir = self.album_dir(platform, album_title)
        if not album_dir.is_dir():
            return None
        try:
            return sum(p.stat().st_size for p in album_dir.rglob("*") if p.is_file())
        except OSError:
            return None

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
            payload = xm_tracks_page(_fetch_json, album_id, page,
                                     referer=f"https://www.ximalaya.com/album/{album_id}")
            if "data" not in payload:
                # 实测下架专辑返回 {"ret": 924, "msg": "该内容因故已下架"}，须透出真实原因。
                raise AlbumOfflineError(payload.get("msg") or f"喜马拉雅曲目接口异常: ret={payload.get('ret')}")
            data = payload["data"]
            for item in data.get("list", []):
                tracks.append(Track(str(item["trackId"]), str(item["title"]), "m4a"))
            if page >= (data.get("maxPageId") or 1):
                return tracks
            page += 1
            time.sleep(self.page_pause_seconds)
        return tracks

    def _list_qingting(self, channel_id: str) -> list[Track]:
        version = _qingting_version(channel_id)
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

    def _list_netease_playlist(self, playlist_id: str) -> list[Track]:
        """歌单曲目：trackIds 给全量 ID，再分批取标题。"""
        payload = _fetch_json(NETEASE_PLAYLIST_URL.format(playlist_id=playlist_id),
                               referer=NETEASE_REFERER)
        playlist = payload.get("playlist") or {}
        ids = [str(item["id"]) for item in (playlist.get("trackIds") or [])]
        titles = self._netease_titles(ids)
        return [Track(track_id, titles.get(track_id, f"曲目 {track_id}"), "mp3")
                for track_id in ids]

    def _list_netease_album(self, album_id: str) -> list[Track]:
        """专辑曲目：/api/v1/album 的 songs 一次全量返回，无需分页。"""
        payload = _fetch_json(NETEASE_ALBUM_URL.format(album_id=album_id),
                               referer=NETEASE_REFERER)
        songs = payload.get("songs") or []
        return [Track(str(song["id"]), str(song.get("name") or f"曲目 {song['id']}"), "mp3")
                for song in songs]

    def _netease_titles(self, track_ids: list[str]) -> dict[str, str]:
        """按批取曲目标题；接口单批上限 200，超出只返回前 200 条。"""
        titles: dict[str, str] = {}
        for start in range(0, len(track_ids), NETEASE_BATCH_SIZE):
            batch = track_ids[start:start + NETEASE_BATCH_SIZE]
            payload = _fetch_json(
                NETEASE_SONG_DETAIL_URL.format(ids=urllib.parse.quote(json.dumps(batch))),
                referer=NETEASE_REFERER)
            for song in payload.get("songs") or []:
                titles[str(song["id"])] = str(song.get("name") or "")
            if start + NETEASE_BATCH_SIZE < len(track_ids):
                time.sleep(self.page_pause_seconds)
        return titles

    def _netease_batch_urls(self, track_ids: list[str]) -> tuple[dict[str, str], dict[str, str]]:
        """批量取直链，返回 (可下载的 url, 跳过原因)。

        实测该接口的返回顺序不保证与请求顺序一致，必须按 id 建字典对齐。
        code=-110 = VIP 付费未放行；code=404 或无 url = 平台无音源。
        """
        urls: dict[str, str] = {}
        reasons: dict[str, str] = {}
        for start in range(0, len(track_ids), NETEASE_BATCH_SIZE):
            batch = track_ids[start:start + NETEASE_BATCH_SIZE]
            payload = _fetch_json(
                NETEASE_PLAYER_URL.format(ids=urllib.parse.quote(json.dumps(batch))),
                referer=NETEASE_REFERER)
            for item in payload.get("data") or []:
                track_id = str(item.get("id"))
                url = item.get("url")
                if url and item.get("code") == 200:
                    urls[track_id] = url
                elif item.get("code") == -110:
                    reasons[track_id] = "VIP 付费曲目，平台未放行"
                else:
                    reasons[track_id] = "平台无可用音源"
            # 接口未返回的曲目同样没有可用音源。
            for track_id in batch:
                if track_id not in urls and track_id not in reasons:
                    reasons[track_id] = "平台无可用音源"
            if start + NETEASE_BATCH_SIZE < len(track_ids):
                time.sleep(self.page_pause_seconds)
        return urls, reasons

    def _download_netease(self, platform: str, album_id: str, album_title: str,
                          on_progress=None) -> DownloadReport:
        """网易云下载：分批取直链再逐首落盘。

        直链有效期约 20 分钟（expi=1200），故边取边下，不一次性拿完再慢慢下。
        """
        tracks = self.list_tracks(platform, album_id)
        album_dir = self.album_dir(platform, album_title)
        album_dir.mkdir(parents=True, exist_ok=True)
        report = DownloadReport()
        for start in range(0, len(tracks), NETEASE_BATCH_SIZE):
            batch = tracks[start:start + NETEASE_BATCH_SIZE]
            urls, reasons = self._netease_batch_urls([track.track_id for track in batch])
            for offset, track in enumerate(batch):
                index = start + offset + 1
                report = self._download_netease_one(track, index, album_dir, report,
                                                    urls.get(track.track_id),
                                                    reasons.get(track.track_id))
                if on_progress:
                    on_progress(index, len(tracks))
                time.sleep(self.throttle_seconds)
        return replace(report, size_bytes=self.album_size_bytes(platform, album_title))

    def _download_netease_one(self, track: Track, index: int, album_dir: Path,
                              report: DownloadReport, url: str | None,
                              reason: str | None) -> DownloadReport:
        dest = album_dir / f"{index:03d}-{sanitize_filename(track.title)}.{track.ext}"
        try:
            if dest.exists():
                return replace(report, downloaded=report.downloaded + 1)
            if not url:
                return replace(report, skipped=report.skipped + 1,
                               skip_reasons=report.skip_reasons + (
                                   SkipReason(track.title, reason or "平台无可用音源"),))
            _download_file(url, dest, referer=NETEASE_REFERER)
            return replace(report, downloaded=report.downloaded + 1)
        except urllib.error.HTTPError as exc:
            # 403/404 = 直链已失效或音源被撤，属不可下载而非网络故障。
            if exc.code in (401, 403, 404):
                return replace(report, skipped=report.skipped + 1,
                               skip_reasons=report.skip_reasons + (
                                   SkipReason(track.title, "音源不可用"),))
            return replace(report, failed=report.failed + 1)
        except Exception:
            return replace(report, failed=report.failed + 1)

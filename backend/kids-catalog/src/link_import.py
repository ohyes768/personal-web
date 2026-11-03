"""手动链接导入：解析专辑链接、预检可下载性。

平台实测结论（2026-10-23，真实请求逐字段核对）：
- 喜马拉雅 mobile 接口 ret=924 = 已下架或不存在（不存在专辑同样返回 924）；
  付费标记在曲目级 isPaid，专辑级没有付费字段（data 只有 list/maxPageId/pageId/pageSize/totalCount）。
- 蜻蜓 capi 接口的付费标记在专辑级 vip_label（"会员畅听"，等价网页榜单侧 sale_type=1）；
  曲目级 isfree=true 标记的是 VIP 专辑里的免费集，不能当付费信号用。
- 2026-10-24 补充：新版曲目接口 mobile/v1/album/track 对一批专辑返回 924（"已下架"），
  但旧接口 mobile/v1/album/single 仍在服务且曲目项字段兼容；曲目列表统一经
  downloader.xm_tracks_page 获取，自动回退。微信分享链接 selfshare/album(new)/{id}
  与 album/{id} 同一专辑号，解析等价。
- 2026-11-02 补充：新增网易云音乐来源（歌单/专辑链接）。实测接口全部免登录：
  歌单 /api/v3/playlist/detail（trackIds 全量，实测 965 首不截断）；
  专辑 /api/v1/album/{id}（songs 一次全量，注意 /api/album/{id} 恒返回空 songs）；
  曲目详情 /api/song/detail/?ids=[...]（单批上限 200）；
  播放直链 /api/song/enhance/player/url?ids=[...&br=128000]（单批上限 200）。
  付费判定用曲目级 fee：8=可下载、1=VIP 无音源（player/url 回 code=-110）。
  网易云歌单是免费曲与 VIP 曲混排，专辑级无法判定，sale_type 统一 None（付费未知）。
"""
import re
import time
import urllib.error
import urllib.parse

from src.downloader import (NETEASE_ALBUM, NETEASE_ALBUM_URL, NETEASE_PLAYLIST,
                            NETEASE_PLAYLIST_URL, NETEASE_REFERER,
                            QT_CHANNEL_URL, QT_PROGRAMS_URL, QT_REFERER,
                            XM_OFFLINE_RET, _fetch_json, xm_tracks_page)

XM_PLATFORM = "喜马拉雅"
QT_PLATFORM = "蜻蜓FM"
VIP_KEYWORD = "会员"
# 预检限速，与采集器的下架预检同款，避免连续请求触发平台风控。
PROBE_PAUSE_SECONDS = 0.2

_XM_ALBUM = re.compile(
    r'^https?://(?:[\w-]+\.)*ximalaya\.com/(?:selfshare/)?album(?:new)?/(\d+)(?:[/?#]|$)', re.I)
_QT_VCHANNEL = re.compile(r'^https?://(?:[\w-]+\.)*qingting\.fm/vchannels/(\d+)(?:[/?#]|$)', re.I)
_XM_SINGLE = re.compile(r'ximalaya\.com/(?:sound|radio|album_sound)/', re.I)
_QT_SINGLE = re.compile(r'qingting\.fm/(?:album|channels)/\d+/(?:audio|\d+)', re.I)
# 网易云歌单/专辑：路径式 /playlist?id= 、/album?id= ，移动版多一层 /m/。
# hash 路由（/#/playlist?id=）由 parse_album_link 先剥掉 # 段再匹配。
# 只匹配路径，id 参数另行从 query 里取，避免 query 参数顺序影响解析。
_NETEASE_PATH = re.compile(
    r'^https?://(?:[\w-]+\.)*music\.163\.com/(?:m/)?(playlist|album)/?$', re.I)
_NETEASE_SINGLE = re.compile(r'music\.163\.com/(?:m/)?song/?\?id=\d+', re.I)
_NETEASE_SHORT = re.compile(r'(?:^|//)163\.cn/', re.I)
_SUPPORTED = ("仅支持专辑链接：喜马拉雅 ximalaya.com/album/{id}"
              "（含微信分享 m.ximalaya.com/selfshare/albumnew/{id}）"
              "、蜻蜓 qingting.fm/vchannels/{id}"
              "，或网易云音乐 music.163.com/playlist?id={id}（歌单）"
              "与 music.163.com/album?id={id}（专辑）")


class LinkImportError(ValueError):
    """用户可读的导入失败原因（付费/下架/链接不识别/网络失败）。"""


def parse_album_link(url: str) -> tuple[str, str]:
    """解析专辑链接为 (platform, album_id)；不支持的链接抛 LinkImportError。

    容忍缺省 scheme、www/m/无子域、尾斜杠与查询参数。
    """
    text = (url or "").strip()
    if not text:
        raise LinkImportError("请填写专辑链接")
    if "://" not in text:
        text = f"https://{text}"
    match = _XM_ALBUM.match(text)
    if match:
        return XM_PLATFORM, match.group(1)
    match = _QT_VCHANNEL.match(text)
    if match:
        return QT_PLATFORM, match.group(1)
    # 网易云 hash 路由（https://music.163.com/#/playlist?id=123）里的 # 之后才是路径，
    # 直接把 # 段接回路径再匹配，两种写法共用同一组正则。
    netease = _parse_netease_link(text)
    if netease:
        return netease
    if _XM_SINGLE.search(text) or _QT_SINGLE.search(text):
        raise LinkImportError(f"单曲链接不支持，请提供专辑链接。{_SUPPORTED}")
    raise LinkImportError(f"无法识别的链接，{_SUPPORTED}")


def _parse_netease_link(text: str) -> tuple[str, str] | None:
    """解析网易云歌单/专辑链接；不是网易云链接返回 None。"""
    if _NETEASE_SHORT.search(text):
        raise LinkImportError(
            f"网易云短链接暂不支持，请复制完整链接（浏览器地址栏整条）。{_SUPPORTED}")
    if _NETEASE_SINGLE.search(text):
        raise LinkImportError(f"单曲链接不支持，请提供歌单或专辑链接。{_SUPPORTED}")
    # hash 路由：把 # 之后的部分当作路径来接在域名后面。
    head, sep, tail = text.partition("#")
    candidates = [text]
    if sep and tail.startswith("/"):
        candidates.append(f"{head.rstrip('/')}{tail}")
    for candidate in candidates:
        path, _, query = candidate.partition("?")
        match = _NETEASE_PATH.match(path)
        if not match:
            continue
        # id 参数在 query 里的位置不固定（?id=1 与 ?userid=1&id=1 都要认）。
        params = urllib.parse.parse_qs(query)
        ids = params.get("id") or []
        if not ids or not ids[0].isdigit():
            raise LinkImportError(f"该网易云链接缺少有效的 id 参数。{_SUPPORTED}")
        platform = (NETEASE_PLAYLIST if match.group(1).lower() == "playlist"
                    else NETEASE_ALBUM)
        return platform, ids[0]
    return None


def probe_album(platform: str, album_id: str) -> dict:
    """预检专辑可下载性，返回目录行数据；付费/下架/不存在抛 LinkImportError。"""
    if platform == XM_PLATFORM:
        return _probe_ximalaya(album_id)
    if platform == QT_PLATFORM:
        return _probe_qingting(album_id)
    if platform == NETEASE_PLAYLIST:
        return _probe_netease_playlist(album_id)
    if platform == NETEASE_ALBUM:
        return _probe_netease_album(album_id)
    raise LinkImportError(f"不支持的下载来源：{platform}")


def _fetch(url: str, referer: str | None = None, label: str = "平台接口") -> dict:
    """网络层统一收口：任何失败都转成用户可读的原因。"""
    try:
        return _fetch_json(url, referer=referer)
    except urllib.error.HTTPError as exc:
        raise LinkImportError(f"{label}返回 HTTP {exc.code}") from None
    except Exception as exc:
        raise LinkImportError(f"网络请求失败：{exc}") from None


def _fetch_xm(url: str, referer: str | None = None) -> dict:
    return _fetch(url, referer=referer, label="喜马拉雅接口")


def _probe_ximalaya(album_id: str) -> dict:
    referer = f"https://www.ximalaya.com/album/{album_id}"
    payload = xm_tracks_page(_fetch_xm, album_id, 1, referer=referer)
    if payload.get("ret") == XM_OFFLINE_RET:
        raise LinkImportError(f"该专辑已被平台下架：{payload.get('msg') or '内容不可访问'}")
    data = payload.get("data") or {}
    if not data:
        raise LinkImportError(f"喜马拉雅接口返回异常：ret={payload.get('ret')}")
    tracks = data.get("list") or []
    if not tracks:
        raise LinkImportError("该专辑没有可读取的曲目")
    title = next((item.get("albumTitle") for item in tracks if item.get("albumTitle")), None)
    if not title:
        raise LinkImportError("未能读取到专辑名称")
    total = data.get("totalCount")
    # 付费判定：首页全是付费曲时再抽末页复核，避免「首页恰好全是免费曲、后面整张收费」被误判为免费专辑。
    if all(bool(item.get("isPaid")) for item in tracks):
        max_page = data.get("maxPageId") or 1
        if not isinstance(max_page, int):
            max_page = 1
        if max_page > 1:
            time.sleep(PROBE_PAUSE_SECONDS)
            last = xm_tracks_page(_fetch_xm, album_id, max_page, referer=referer)
            last_tracks = ((last.get("data") or {}).get("list") or [])
            whole_paid = not last_tracks or all(bool(item.get("isPaid")) for item in last_tracks)
        else:
            whole_paid = True
        if whole_paid:
            raise LinkImportError("付费专辑不支持下载")
    return {
        "platform": XM_PLATFORM, "album_id": album_id, "title": title,
        "url": f"https://www.ximalaya.com/album/{album_id}",
        "sale_type": 0,
        "track_count": total if isinstance(total, int) else len(tracks),
    }


def _probe_qingting(channel_id: str) -> dict:
    try:
        channel = _fetch_json(QT_CHANNEL_URL.format(channel_id=channel_id), referer=QT_REFERER)
    except urllib.error.HTTPError as exc:
        if exc.code == 400:
            raise LinkImportError("未找到该蜻蜓专辑，编号可能不正确") from None
        raise LinkImportError(f"蜻蜓接口返回 HTTP {exc.code}") from None
    except Exception as exc:
        raise LinkImportError(f"网络请求失败：{exc}") from None
    data = channel.get("data") or {}
    if not data:
        raise LinkImportError("未找到该蜻蜓专辑，编号可能不正确")
    # 实测会员专辑的标签是「会员畅听」；按「会员」二字判定可覆盖平台换文案（如会员专享）的同类标签。
    # str() 兜底：标签类型异常时按文本比对，不因类型错误抛 500。
    if VIP_KEYWORD in str(data.get("vip_label") or ""):
        raise LinkImportError("付费专辑不支持下载")
    title, version = data.get("title"), data.get("v")
    if not title or not version:
        raise LinkImportError("未能读取到蜻蜓专辑信息")
    time.sleep(PROBE_PAUSE_SECONDS)
    programs = _fetch(f"{QT_PROGRAMS_URL.format(channel_id=channel_id, version=version)}"
                      "?curpage=1&pagesize=30&order=asc", referer=QT_REFERER, label="蜻蜓接口")
    pdata = programs.get("data") or {}
    total = pdata.get("total")
    return {
        "platform": QT_PLATFORM, "album_id": channel_id, "title": title,
        "url": f"https://m.qingting.fm/vchannels/{channel_id}/",
        "sale_type": 0,
        "track_count": total if isinstance(total, int) else len(pdata.get("programs") or []),
    }


def _fetch_netease(url: str) -> dict:
    return _fetch(url, referer=NETEASE_REFERER, label="网易云接口")


def _probe_netease_playlist(playlist_id: str) -> dict:
    """预检网易云歌单：trackIds 给出完整曲目 ID 列表（实测不截断）。"""
    payload = _fetch_netease(NETEASE_PLAYLIST_URL.format(playlist_id=playlist_id))
    if payload.get("code") == 404:
        raise LinkImportError("未找到该网易云歌单，编号可能不正确")
    playlist = payload.get("playlist") or {}
    if not playlist:
        raise LinkImportError("未找到该网易云歌单，编号可能不正确")
    title = playlist.get("name")
    if not title:
        raise LinkImportError("未能读取到歌单名称")
    track_ids = playlist.get("trackIds") or []
    if not track_ids:
        raise LinkImportError("该歌单没有可读取的曲目")
    total = playlist.get("trackCount")
    return {
        "platform": NETEASE_PLAYLIST, "album_id": playlist_id, "title": title,
        "url": f"https://music.163.com/playlist?id={playlist_id}",
        # 网易云歌单是免费曲与 VIP 曲混排，专辑级无法判定付费，逐曲在下载时处理。
        "sale_type": None,
        "track_count": total if isinstance(total, int) else len(track_ids),
    }


def _probe_netease_album(album_id: str) -> dict:
    """预检网易云专辑：/api/v1/album 的 songs 一次全量返回。"""
    payload = _fetch_netease(NETEASE_ALBUM_URL.format(album_id=album_id))
    if payload.get("code") == 404:
        raise LinkImportError("未找到该网易云专辑，编号可能不正确")
    album = payload.get("album") or {}
    if not album:
        raise LinkImportError("未找到该网易云专辑，编号可能不正确")
    title = album.get("name")
    if not title:
        raise LinkImportError("未能读取到专辑名称")
    songs = payload.get("songs") or []
    if not songs:
        raise LinkImportError("该专辑没有可读取的曲目")
    total = album.get("size")
    return {
        "platform": NETEASE_ALBUM, "album_id": album_id, "title": title,
        "url": f"https://music.163.com/album?id={album_id}",
        "sale_type": None,
        "track_count": total if isinstance(total, int) else len(songs),
    }

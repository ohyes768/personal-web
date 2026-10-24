"""手动链接导入：解析专辑链接、预检可下载性。

平台实测结论（2026-10-23，真实请求逐字段核对）：
- 喜马拉雅 mobile 接口 ret=924 = 已下架或不存在（不存在专辑同样返回 924）；
  付费标记在曲目级 isPaid，专辑级没有付费字段（data 只有 list/maxPageId/pageId/pageSize/totalCount）。
- 蜻蜓 capi 接口的付费标记在专辑级 vip_label（"会员畅听"，等价网页榜单侧 sale_type=1）；
  曲目级 isfree=true 标记的是 VIP 专辑里的免费集，不能当付费信号用。
"""
import re
import time
import urllib.error

from src.downloader import (PAGE_SIZE, QT_CHANNEL_URL, QT_PROGRAMS_URL, QT_REFERER,
                            XM_OFFLINE_RET, XM_TRACKS_URL, _fetch_json)

XM_PLATFORM = "喜马拉雅"
QT_PLATFORM = "蜻蜓FM"
VIP_KEYWORD = "会员"
# 预检限速，与采集器的下架预检同款，避免连续请求触发平台风控。
PROBE_PAUSE_SECONDS = 0.2

_XM_ALBUM = re.compile(r'^https?://(?:[\w-]+\.)*ximalaya\.com/album/(\d+)(?:[/?#]|$)', re.I)
_QT_VCHANNEL = re.compile(r'^https?://(?:[\w-]+\.)*qingting\.fm/vchannels/(\d+)(?:[/?#]|$)', re.I)
_XM_SINGLE = re.compile(r'ximalaya\.com/(?:sound|radio|album_sound)/', re.I)
_QT_SINGLE = re.compile(r'qingting\.fm/(?:album|channels)/\d+/(?:audio|\d+)', re.I)
_SUPPORTED = "仅支持专辑链接：喜马拉雅 ximalaya.com/album/{id} 或蜻蜓 qingting.fm/vchannels/{id}"


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
    if _XM_SINGLE.search(text) or _QT_SINGLE.search(text):
        raise LinkImportError(f"单曲链接不支持，请提供专辑链接。{_SUPPORTED}")
    raise LinkImportError(f"无法识别的链接，{_SUPPORTED}")


def probe_album(platform: str, album_id: str) -> dict:
    """预检专辑可下载性，返回目录行数据；付费/下架/不存在抛 LinkImportError。"""
    if platform == XM_PLATFORM:
        return _probe_ximalaya(album_id)
    if platform == QT_PLATFORM:
        return _probe_qingting(album_id)
    raise LinkImportError(f"不支持的下载来源：{platform}")


def _fetch(url: str, referer: str | None = None, label: str = "平台接口") -> dict:
    """网络层统一收口：任何失败都转成用户可读的原因。"""
    try:
        return _fetch_json(url, referer=referer)
    except urllib.error.HTTPError as exc:
        raise LinkImportError(f"{label}返回 HTTP {exc.code}") from None
    except Exception as exc:
        raise LinkImportError(f"网络请求失败：{exc}") from None


def _probe_ximalaya(album_id: str) -> dict:
    payload = _fetch(f"{XM_TRACKS_URL}?albumId={album_id}&pageSize={PAGE_SIZE}&pageId=1",
                     referer=f"https://www.ximalaya.com/album/{album_id}", label="喜马拉雅接口")
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
            last = _fetch(f"{XM_TRACKS_URL}?albumId={album_id}&pageSize={PAGE_SIZE}&pageId={max_page}",
                          referer=f"https://www.ximalaya.com/album/{album_id}", label="喜马拉雅接口")
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

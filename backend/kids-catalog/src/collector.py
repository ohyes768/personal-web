"""Collect strict 0-1-year-old album candidates: official OpenAPI first, public web APIs as fallback."""
import json
import logging
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from src.downloader import track_total, ximalaya_album_available
from src.ximalaya import CredentialsMissing, XimalayaClient, collect_ximalaya_official

logger = logging.getLogger(__name__)

QT_URL = "https://m.qingting.fm/categories/1599/attrs/4394/"
XM_WEB_BASE = "https://www.ximalaya.com"
# 喜马拉雅网页版公开 JSON 接口（频道元数据体系，免登录免签名）。
XM_GROUP_ALL = f"{XM_WEB_BASE}/revision/metadata/v2/group/all"
XM_GROUP_CHANNELS = f"{XM_WEB_BASE}/revision/metadata/v2/group/channels"
XM_CHANNEL_ALBUMS = f"{XM_WEB_BASE}/revision/metadata/v2/channel/albums"
XM_KIDS_GROUP = "儿童"
# 只收儿歌/哄睡频道：其他儿童频道（故事/科普等）受众偏 3 岁以上。
XM_WANTED_CHANNELS = ("儿歌", "哄睡")
# 每个平台源保留的专辑上限（蜻蜓 + 喜马拉雅 = 共 20 张，全部免费内容）。
PER_PLATFORM_LIMIT = 10
INFANT = re.compile(r"(?:0\s*[-~～至到]\s*1\s*岁|0\s*岁\s*(?:\+|以上)|婴儿|婴幼儿)")
TODDLER = re.compile(r"0\s*[-~～至到]\s*[23]\s*岁")
# 哄睡频道热门榜混有学龄故事与成人助眠节目，须含婴幼儿向词才按场景推断收录。
INFANTISH = re.compile(r"宝宝|婴儿|婴幼|宝贝|摇篮|晚安|睡前故事|童话|幼儿")
SCHOOL_AGE = re.compile(r"上学|小学|一年级|二年级|校园|笑话")


def _read(url: str) -> str:
    request = Request(url, headers={"User-Agent": "KidsCatalog/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def collect_qingting() -> list[dict]:
    robots = RobotFileParser()
    robots.parse(_read("https://m.qingting.fm/robots.txt").splitlines())
    if not robots.can_fetch("KidsCatalog", QT_URL):
        raise RuntimeError("蜻蜓FM robots 不允许访问0-1岁目录")
    soup = BeautifulSoup(_read(QT_URL), "html.parser")
    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        match = re.search(r"window\.__initStores\s*=\s*", text)
        if not match:
            continue
        state = json.JSONDecoder().raw_decode(text[match.end():])[0]
        items = state.get("AttributeStore", {}).get("FilterList", [])
        rows = []
        for item in items:
            if item.get("category_id") != 1599 or not item.get("id") or not item.get("title"):
                continue
            # 会员专辑下载环节只会被跳过，不占免费内容的 10 个名额。
            if item.get("sale_type") == 1:
                continue
            rows.append({
                    "platform": "蜻蜓FM", "album_id": str(item["id"]),
                    "title": item["title"],
                    "url": f"https://m.qingting.fm/vchannels/{item['id']}/",
                    "age_evidence": "蜻蜓FM年龄筛选", "age_confidence": "高",
                    "sale_type": item.get("sale_type", 0),
                })
        if rows:
            return rows[:PER_PLATFORM_LIMIT]
    raise RuntimeError("蜻蜓FM 0-1岁目录没有返回候选")


def _get_json(url: str, **params: str) -> dict:
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "KidsCatalog/1.0"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def collect_ximalaya_web() -> list[dict]:
    """喜马拉雅网页版频道热门榜：儿童组下儿歌/哄睡频道的最多播放专辑。

    平台对儿童内容不提供年龄元数据，年龄证据按三级判定：
    标题/简介明确 0-1 岁（高）→ 低龄标注 0-2/0-3 岁推断（中）→ 哄睡场景推断（中）；
    儿歌频道无年龄标注的不收，避免混入 3 岁以上内容。
    """
    groups = _get_json(XM_GROUP_ALL)["data"]["groups"]
    kids_group = next((g for g in groups if g["name"] == XM_KIDS_GROUP), None)
    if not kids_group:
        raise RuntimeError("喜马拉雅网页版没有儿童分组")
    channels = _get_json(XM_GROUP_CHANNELS, groupId=str(kids_group["id"]))["data"]["channels"]
    wanted = {c["channelName"]: c["relationMetadataValueId"] for c in channels
              if c["channelName"] in XM_WANTED_CHANNELS}
    if not wanted:
        raise RuntimeError("喜马拉雅儿童分组下没有儿歌/哄睡频道")

    rows: list[dict] = []
    for channel_name, metadata_value_id in wanted.items():
        data = _get_json(XM_CHANNEL_ALBUMS, metadataValueId=str(metadata_value_id),
                         page="1", perPage="50", sort="3")["data"]
        for album in data.get("albums", []):
            # 会员专辑下载环节只会被跳过，不占免费内容的名额。
            if album.get("isPaid") is True:
                continue
            text = f"{album['albumTitle']} {album.get('intro') or ''}"
            if INFANT.search(text):
                evidence, confidence = f"喜马拉雅{channel_name}频道热门榜，标注 0-1 岁", "高"
            elif TODDLER.search(text):
                evidence, confidence = f"喜马拉雅{channel_name}频道热门榜，标注 0-2/0-3 岁低龄推断", "中"
            elif channel_name == "哄睡" and INFANTISH.search(text) and not SCHOOL_AGE.search(text):
                evidence, confidence = "喜马拉雅哄睡频道热门榜，婴幼儿向哄睡内容推断", "中"
            else:
                continue
            # 网页热门榜按历史播放量排序，会残留已下架专辑（榜单与曲库不同步）；
            # 用下载同款移动端接口预检，下架的不占免费内容名额。
            album_id = str(album["albumId"])
            try:
                alive = ximalaya_album_available(album_id)
            except Exception:
                alive = True  # 预检网络失败时保守收录，下载环节仍有 unavailable 兜底。
            if not alive:
                continue
            time.sleep(0.2)  # 预检限速，避免连续请求触发移动端接口风控。
            rows.append({
                "platform": "喜马拉雅", "album_id": album_id,
                "title": album["albumTitle"],
                "url": f"{XM_WEB_BASE}/album/{album['albumId']}",
                "age_evidence": evidence, "age_confidence": confidence,
                "sale_type": {True: 1, False: 0}.get(album.get("isPaid")),
            })
    return rows[:PER_PLATFORM_LIMIT]


def collect_latest() -> list[dict]:
    rows: list[dict] = []
    # 优先官方开放平台（凭据未配置或平台无儿童内容时跳过，不视为错误）。
    try:
        rows.extend(collect_ximalaya_official(XimalayaClient.from_env()))
    except CredentialsMissing:
        pass
    except Exception:
        logger.warning("喜马拉雅开放平台采集不可用，回退网页采集", exc_info=True)
    try:
        rows.extend(collect_qingting())
    except Exception:
        logger.warning("蜻蜓FM采集不可用", exc_info=True)
    try:
        rows.extend(collect_ximalaya_web())
    except Exception:
        # Web scraping is best-effort; Qingting remains a valid high-confidence result.
        logger.warning("喜马拉雅网页采集不可用", exc_info=True)
    unique = {(row["platform"], row["album_id"]): row for row in rows}
    # 下载前成本提示：为每张候选附曲目总数；单张取数失败不阻塞采集（显示端留空）。
    counted: list[dict] = []
    for row in unique.values():
        try:
            total = track_total(row["platform"], row["album_id"])
        except Exception:
            logger.warning("曲目总数获取失败: %s %s", row["platform"], row["title"])
            total = None
        counted.append({**row, "track_count": total})
        time.sleep(0.2)  # 与下架预检同款限速，避免触发平台风控。
    return counted
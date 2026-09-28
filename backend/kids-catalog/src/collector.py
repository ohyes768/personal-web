"""Collect strict 0-1-year-old album candidates from public catalogue pages."""
import json
import re
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

QT_URL = "https://m.qingting.fm/categories/1599/attrs/4394/"
XM_URL = "https://www.ximalaya.com/top/5/100092"
INFANT = re.compile(r"(?:0\s*[-~～至到]\s*1\s*岁|0\s*岁\s*(?:\+|以上)|婴儿|婴幼儿)")


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
            if item.get("category_id") == 1599 and item.get("id") and item.get("title"):
                rows.append({
                    "platform": "蜻蜓FM", "album_id": str(item["id"]),
                    "title": item["title"],
                    "url": f"https://m.qingting.fm/vchannels/{item['id']}/",
                    "age_evidence": "蜻蜓FM年龄筛选", "age_confidence": "高",
                })
        if rows:
            return rows[:15]
    raise RuntimeError("蜻蜓FM 0-1岁目录没有返回候选")


def collect_ximalaya() -> list[dict]:
    soup = BeautifulSoup(_read(XM_URL), "html.parser")
    rows = []
    for item in soup.select(".album-item"):
        category = item.select_one(".user-category_title")
        anchor = item.select_one('a[href^="/album/"]')
        title = item.select_one(".title")
        description = item.select_one(".description")
        if not category or category.get_text(strip=True) != "儿童" or not anchor or not title:
            continue
        declared = " ".join((title.get_text(" ", strip=True), description.get_text(" ", strip=True) if description else ""))
        if not INFANT.search(declared):
            continue
        match = re.fullmatch(r"/album/(\d+)/?", anchor.get("href", ""))
        if match:
            rows.append({
                "platform": "喜马拉雅", "album_id": match.group(1),
                "title": title.get_text(strip=True),
                "url": f"https://www.ximalaya.com/album/{match.group(1)}",
                "age_evidence": "详情简介明确年龄标注", "age_confidence": "中",
            })
    return rows[:15]


def collect_latest() -> list[dict]:
    rows = collect_qingting()
    try:
        rows.extend(collect_ximalaya())
    except Exception:
        # Qingting remains a valid high-confidence result if Ximalaya is temporarily unavailable.
        pass
    unique = {(row["platform"], row["album_id"]): row for row in rows}
    return list(unique.values())
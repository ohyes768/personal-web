"""
RSS 2.0 订阅源工具函数
为 /api/rss.xml 端点提供 XML 转义、CDATA 安全、日期格式化、hashtag 提取、摘要截断和 RSS 文档拼装。

为什么手写不用 feedgen：项目零 XML 依赖，RSS 2.0 模板固定，手写 ~120 行足够可控。
"""

import re
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime as _email_format_datetime
from typing import Any


# XML 实体转义表（& 必须第一个，否则双重转义）
_XML_ESCAPE_MAP = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&apos;",
}

# RSS 中常见的不安全字符：CDATA 段内唯一不能出现的是 ]]>
_CDATA_END = "]]>"
_CDATA_SAFE_REPLACEMENT = "]]]]><![CDATA[>"


def xml_escape(s: str) -> str:
    """XML 5 字符实体转义。None 安全。

    Args:
        s: 待转义字符串（可能含 & < > " '）

    Returns:
        转义后的字符串
    """
    if not s:
        return ""
    result = s
    for char, entity in _XML_ESCAPE_MAP.items():
        result = result.replace(char, entity)
    return result


def cdata_safe(text: str) -> str:
    """CDATA 段内防 ]]> 中断：把 ]]> 拆成 ]]]]><![CDATA[>。

    Args:
        text: 原始文本（即将放入 <![CDATA[...]]> 内的内容）

    Returns:
        处理后的安全文本
    """
    if not text:
        return ""
    return text.replace(_CDATA_END, _CDATA_SAFE_REPLACEMENT)


def format_rfc822(dt: datetime) -> str:
    """日期转 RFC 822 格式（RSS 2.0 pubDate/lastBuildDate 规范）。

    强制 +0800 (东八区)，naive datetime 视为本地时间。

    Args:
        dt: datetime 对象

    Returns:
        'Mon, 25 Jun 2026 09:57:36 +0800' 格式字符串
    """
    if dt.tzinfo is None:
        # naive datetime 视为东八区
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
    return _email_format_datetime(dt, usegmt=False).replace("GMT", "+0800")


def extract_hashtags(description: str, max_n: int = 5) -> list[str]:
    """从 description 提取 #xxx 标签。

    支持中文/英文/数字/下划线。保序去重。

    Args:
        description: 抖音视频描述
        max_n: 最多返回几个

    Returns:
        hashtag 列表（不含 # 前缀）
    """
    if not description:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for tag in re.findall(r"#([\w\u4e00-\u9fa5]+)", description):
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
            if len(result) >= max_n:
                break
    return result


def truncate_for_summary(text: str, n: int = 200) -> str:
    """取前 n 字作为摘要。避免截半字，末尾加省略号。

    Args:
        text: 完整文本
        n: 字数上限

    Returns:
        截断后的摘要（< n 字时不加 ...）
    """
    if not text:
        return ""
    # 先去首尾空白
    text = text.strip()
    if len(text) <= n:
        return text
    # 截到 n 字符，再按 rsplit 找一个安全的截断点（避免半个汉字）
    truncated = text[:n]
    # 如果末尾是半个汉字（高代理 0xD800-0xDBFF），回退 1 字符
    if truncated and 0xD800 <= ord(truncated[-1]) <= 0xDBFF:
        truncated = truncated[:-1]
    return truncated.rstrip() + "..."


def build_rss_xml(
    channel_meta: dict,
    items: list[dict],
    build_date: datetime,
) -> str:
    """拼装完整 RSS 2.0 文档字符串。

    Args:
        channel_meta: {title, link, description, self_url}
        items: [{
            title, link, description, author, categories, pub_date, guid, content_encoded
        }]
        build_date: lastBuildDate 用

    Returns:
        完整 RSS XML 字符串（带 XML 头）
    """
    last_build = format_rfc822(build_date)

    # Channel 顶层
    channel_parts = [
        "    <title>" + xml_escape(channel_meta.get("title", "")) + "</title>",
        "    <link>" + xml_escape(channel_meta.get("link", "")) + "</link>",
        "    <description>" + xml_escape(channel_meta.get("description", "")) + "</description>",
        "    <language>zh-CN</language>",
        f"    <lastBuildDate>{last_build}</lastBuildDate>",
        "    <ttl>300</ttl>",
        '    <atom:link href="'
        + xml_escape(channel_meta.get("self_url", ""))
        + '" rel="self" type="application/rss+xml" />',
    ]

    # Items
    item_xml_list = []
    for item in items:
        item_parts = ["    <item>"]
        item_parts.append("      <title>" + xml_escape(item.get("title", "")) + "</title>")
        item_parts.append("      <link>" + xml_escape(item.get("link", "")) + "</link>")
        item_parts.append(
            "      <description>" + xml_escape(item.get("description", "")) + "</description>"
        )
        item_parts.append("      <author>" + xml_escape(item.get("author", "")) + "</author>")

        for cat in item.get("categories", []):
            item_parts.append("      <category>" + xml_escape(cat) + "</category>")

        pub_date = item.get("pub_date")
        if pub_date is not None:
            item_parts.append(
                "      <pubDate>" + format_rfc822(pub_date) + "</pubDate>"
            )

        item_parts.append(
            '      <guid isPermaLink="false">'
            + xml_escape(str(item.get("guid", "")))
            + "</guid>"
        )

        # content:encoded 用 CDATA 包裹（防 ]]> 截断）
        content_encoded = cdata_safe(item.get("content_encoded", ""))
        item_parts.append(
            "      <content:encoded><![CDATA[" + content_encoded + "]]></content:encoded>"
        )

        item_parts.append("    </item>")
        item_xml_list.append("\n".join(item_parts))

    items_xml = "\n".join(item_xml_list)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"'
        ' xmlns:atom="http://www.w3.org/2005/Atom"'
        ' xmlns:content="http://purl.org/rss/1.0/modules/content/">\n'
        "  <channel>\n"
        + "\n".join(channel_parts)
        + "\n"
        + (items_xml + "\n" if items_xml else "")
        + "  </channel>\n"
        "</rss>\n"
    )

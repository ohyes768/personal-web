"""API 路由定义：POST /api/post + GET /api/rss.xml + GET /health + GET /"""

import hmac
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import markdown
from fastapi import APIRouter, HTTPException, Query, Request, Response
from loguru import logger
from pydantic import BaseModel, Field
from pydantic import ValidationError
from .channels import ChannelRegistry, ChannelCreate, ChannelUpdate, CHANNEL_PATTERN, UNCLASSIFIED

from .rss_utils import build_rss_xml, truncate_for_summary
from .store import generate_id, write_post, list_posts, delete_post as delete_post_file


EAST8 = timezone(timedelta(hours=8))

router = APIRouter()

# 模块级配置（main.py 启动时通过 set_xxx 注入）
_POSTS_DIR: Path = Path("data/posts")
_RETENTION_DAYS: int = 15
_RSS_CHANNEL_META: dict = {}
_RSS_MAX_ITEMS: int = 200
_RSS_DEFAULT_LIMIT: int = 50
_RSS_TOKEN: str = ""
_CHANNELS: ChannelRegistry | None = None


def set_channel_registry(registry: ChannelRegistry) -> None:
    global _CHANNELS
    _CHANNELS = registry


def channel_registry() -> ChannelRegistry:
    if _CHANNELS is None:
        raise HTTPException(503, "Channel registry unavailable")
    return _CHANNELS


@router.get("/api/channels")
async def get_channels(include_disabled: bool = False):
    return {"channels": channel_registry().list(include_disabled)}


@router.post("/api/channels", status_code=201)
async def create_channel(req: ChannelCreate):
    try:
        return channel_registry().create(req.model_dump())
    except FileExistsError:
        raise HTTPException(409, "Channel already exists")
    except OSError:
        raise HTTPException(503, "Could not save channel")


@router.patch("/api/channels/{channel_id}")
async def update_channel(channel_id: str, req: ChannelUpdate):
    try:
        return channel_registry().update(channel_id, req.model_dump(exclude_unset=True))
    except KeyError:
        raise HTTPException(404, "Channel not found")
    except (ValueError, ValidationError):
        raise HTTPException(422, "Invalid channel update")
    except OSError:
        raise HTTPException(503, "Could not save channel")


def set_storage_config(posts_dir: Path, retention_days: int) -> None:
    global _POSTS_DIR, _RETENTION_DAYS
    _POSTS_DIR = posts_dir
    _RETENTION_DAYS = retention_days


def set_rss_config(channel_meta: dict, max_items: int, default_limit: int) -> None:
    global _RSS_CHANNEL_META, _RSS_MAX_ITEMS, _RSS_DEFAULT_LIMIT
    _RSS_CHANNEL_META = channel_meta
    _RSS_MAX_ITEMS = max_items
    _RSS_DEFAULT_LIMIT = default_limit


def set_rss_token(token: str) -> None:
    """注入 RSS 鉴权 token（main.py 启动时调用，从 RSS_RELAY_TOKEN env 读取）"""
    global _RSS_TOKEN
    _RSS_TOKEN = token or ""


def _verify_rss_token(token: str) -> bool:
    """constant-time token 校验（防时序攻击）

    未配置 token 时直接拒绝（避免误以为已加保护）。
    """
    if not _RSS_TOKEN:
        return False
    if len(token) != len(_RSS_TOKEN):
        return False
    return hmac.compare_digest(token, _RSS_TOKEN)



class PostRequest(BaseModel):
    title: str = Field(..., min_length=1, description="文章标题")
    content: str = Field(..., min_length=1, description="Markdown 正文")
    url: str | None = Field(None, description="原文链接（可选）")
    source: str | None = Field(None, description="来源标识（可选，如 openclaw）")
    channel: str | None = Field(None, max_length=64, pattern=CHANNEL_PATTERN, description="已登记的内容渠道，省略归未分类")


@router.post("/api/post", status_code=201)
async def create_post(req: PostRequest):
    """接收 agent 推送的 markdown。

    无鉴权（依赖内网隔离）。后续如需加 token，参考 douyin 的 ?token= 模式。
    """
    channel_id = req.channel or UNCLASSIFIED
    channel = channel_registry().get(channel_id)
    if channel is None:
        raise HTTPException(422, "Unknown channel; create it first")
    if not channel["enabled"]:
        raise HTTPException(409, "Channel is disabled")
    post_id = generate_id()
    created_at = datetime.now(EAST8)
    file_path = write_post(
        posts_dir=_POSTS_DIR,
        post_id=post_id,
        title=req.title,
        content=req.content,
        url=req.url,
        source=req.source,
        created_at=created_at,
        channel=channel_id,
    )
    logger.info(
        f"接收推送 id={post_id} title={req.title!r} source={req.source!r}"
    )
    return {
        "id": post_id,
        "created_at": created_at.isoformat(),
        "file": str(file_path).replace("\\", "/"),
    }


@router.get("/api/rss.xml")
async def rss_feed(
    request: Request,
    token: str = Query(..., description="RSS 订阅 token（RSS_RELAY_TOKEN）"),
    limit: int = Query(default=None, ge=1, le=200, description="返回条目数上限"),
    channel: str | None = Query(default=None, description="渠道标识；省略返回全部"),
):
    """RSS 2.0 feed。

    鉴权：query string `?token=xxx`，token 来自 RSS_RELAY_TOKEN 环境变量。
    FreshRSS / Feedly 等阅读器在订阅 URL 里带 ?token=xxx 即可。
    """
    if not _verify_rss_token(token):
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(f"RSS 鉴权失败: remote={client_ip}")
        raise HTTPException(status_code=401, detail="Unauthorized")

    channel_meta = dict(_RSS_CHANNEL_META)
    if channel is not None:
        record = channel_registry().get(channel)
        if record is None:
            raise HTTPException(404, "Channel not found")
        channel_meta.update(title=record["title"], description=record["description"])

    requested_limit = limit
    if limit is None:
        limit = _RSS_DEFAULT_LIMIT
    limit = min(limit, _RSS_MAX_ITEMS)

    public_url = channel_meta.get("self_url") or channel_meta.get("link")
    if not public_url:
        raise HTTPException(503, "Public RSS URL not configured")
    parts = urlsplit(public_url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key not in {"token", "channel", "limit"}]
    query.append(("token", token))
    if channel is not None:
        query.append(("channel", channel))
    if requested_limit is not None:
        query.append(("limit", str(limit)))
    self_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))

    posts = list_posts(_POSTS_DIR, limit=limit, max_age_days=_RETENTION_DAYS, channel=channel)

    items = []
    for post in posts:
        content_html = markdown.markdown(
            post["content"], extensions=["extra", "sane_lists", "nl2br"]
        )
        source = post.get("source") or ""
        items.append({
            "title": post["title"],
            "link": post.get("url", ""),
            "description": truncate_for_summary(post["content"], 200),
            "author": source,
            "categories": [source] if source else [],
            "pub_date": post["created_at"],
            "guid": post["id"],
            "content_encoded": content_html,
        })

    build_date = max(
        (p["created_at"] for p in posts),
        default=datetime.now(EAST8),
    )

    xml = build_rss_xml(
        channel_meta={**channel_meta, "self_url": self_url},
        items=items,
        build_date=build_date,
    )

    return Response(
        content=xml,
        media_type="application/rss+xml; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Robots-Tag": "noindex",
        },
    )


@router.get("/api/posts")
async def list_posts_json(
    limit: int = Query(50, ge=1, le=200, description="返回条目数上限"),
    channel: str | None = Query(None, description="渠道标识；省略返回全部，停用渠道仍可查看历史"),
):
    """JSON 列表（前端用，无需 token）。

    与 /api/rss.xml 的区别：
    - 返回 JSON 而非 XML
    - 不要求 token（前端 BFF 内部调用，nginx 限制只能内网走）
    - 含完整 content（前端 Modal 直接渲染，省一次详情请求）
    """
    if channel is not None and channel_registry().get(channel) is None:
        raise HTTPException(404, "Channel not found")
    posts = list_posts(_POSTS_DIR, limit=limit, max_age_days=_RETENTION_DAYS, channel=channel)
    return {
        "total": len(posts),
        "posts": [
            {
                "id": p["id"],
                "title": p["title"],
                "url": p["url"],
                "source": p["source"],
                "channel": p["channel"],
                "created_at": p["created_at"].isoformat(),
                "content": p["content"],
                "preview": truncate_for_summary(p["content"], 200),
            }
            for p in posts
        ],
    }


@router.delete("/api/posts/{post_id}", status_code=204)
async def remove_post(post_id: str):
    """删除一篇 post。无鉴权（依赖内网隔离）。

    204 = 删除成功；404 = 文件不存在或 id 非法（路径分隔符、.. 等）。
    """
    deleted = delete_post_file(_POSTS_DIR, post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found")
    logger.info(f"删除 post id={post_id!r}")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/")
async def root():
    """根路径：服务信息"""
    post_count = (
        sum(1 for _ in _POSTS_DIR.glob("*.md")) if _POSTS_DIR.exists() else 0
    )
    return {
        "service": "rss-relay",
        "version": "1.0.0",
        "description": "个人 RSS 中转",
        "feed": "/api/rss.xml",
        "post_count": post_count,
        "retention_days": _RETENTION_DAYS,
    }

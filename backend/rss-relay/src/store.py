"""markdown 文件存储：写、解析、列表。

文件格式：
    ---
    id: 20260702-143052-a1b2c3
    title: "OpenAI 发布 GPT-5"
    url: "https://..."
    source: "openclaw"
    created_at: "2026-07-02T14:30:52+08:00"
    ---

    # 正文 markdown ...
"""

import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

EAST8 = timezone(timedelta(hours=8))


def generate_id() -> str:
    """生成 post id：{YYYYMMDDHHMMSS}-{6位hex随机}"""
    ts = datetime.now(EAST8).strftime("%Y%m%d-%H%M%S")
    rand = secrets.token_hex(3)  # 6 位 hex
    return f"{ts}-{rand}"


def write_post(
    posts_dir: Path,
    post_id: str,
    title: str,
    content: str,
    url: str | None = None,
    source: str | None = None,
    created_at: datetime | None = None,
) -> Path:
    """写一个 post 文件，返回路径。

    用 yaml.safe_dump 序列化 front matter（自动处理引号转义）。
    """
    if created_at is None:
        created_at = datetime.now(EAST8)

    meta = {
        "id": post_id,
        "title": title,
        "url": url or "",
        "source": source or "",
        "created_at": created_at.isoformat(),
    }

    front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    body = f"---\n{front}---\n\n{content}"

    posts_dir.mkdir(parents=True, exist_ok=True)
    file_path = posts_dir / f"{post_id}.md"
    file_path.write_text(body, encoding="utf-8")
    return file_path


def parse_post(file_path: Path) -> dict | None:
    """解析一个 post 文件，返回字段 dict。

    损坏/格式不对返回 None（容错，让调用方跳过）。
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    if not text.startswith("---"):
        return None

    # 切出 front matter 和 body
    rest = text[3:]
    end_idx = rest.find("\n---")
    if end_idx == -1:
        return None

    front_str = rest[:end_idx]
    body = rest[end_idx + 4:].lstrip("\n")  # 跳过 \n---

    try:
        meta = yaml.safe_load(front_str) or {}
    except yaml.YAMLError:
        return None

    if not isinstance(meta, dict):
        return None

    created_at_str = meta.get("created_at", "")
    try:
        created_at = datetime.fromisoformat(created_at_str) if created_at_str else None
    except (ValueError, TypeError):
        created_at = None

    # created_at 缺失时用文件 mtime 兜底
    if created_at is None:
        try:
            created_at = datetime.fromtimestamp(file_path.stat().st_mtime, EAST8)
        except Exception:
            return None

    return {
        "id": meta.get("id") or file_path.stem,
        "title": meta.get("title", "") or "",
        "url": meta.get("url", "") or "",
        "source": meta.get("source", "") or "",
        "created_at": created_at,
        "content": body,
    }


def list_posts(
    posts_dir: Path,
    limit: int = 50,
    max_age_days: int = 15,
) -> list[dict]:
    """列出最近 max_age_days 天内的 post，按 created_at 倒序，取前 limit 条。"""
    if not posts_dir.exists():
        return []

    cutoff = datetime.now(EAST8) - timedelta(days=max_age_days)

    posts: list[dict] = []
    for f in posts_dir.glob("*.md"):
        post = parse_post(f)
        if post is None:
            continue
        if post["created_at"] < cutoff:
            continue
        posts.append(post)

    posts.sort(key=lambda p: p["created_at"], reverse=True)
    return posts[:limit]


def _validate_post_id(post_id: str) -> bool:
    """校验 post_id 合法：非空、不含路径分隔符/..、长度合理。

    防止 delete_post 被路径穿越攻击（即使只内部使用，也要防一手）。
    """
    if not post_id:
        return False
    if "/" in post_id or "\\" in post_id:
        return False
    if ".." in post_id:
        return False
    if len(post_id) > 200:
        return False
    return True


def delete_post(posts_dir: Path, post_id: str) -> bool:
    """删除一个 post 文件。返回是否真的删了一个文件。

    返回 True = 文件存在并已 unlink；False = id 非法或文件不存在。
    调用方根据返回值翻译为 204 / 404。
    """
    if not _validate_post_id(post_id):
        return False
    file_path = posts_dir / f"{post_id}.md"
    if not file_path.exists():
        return False
    file_path.unlink()
    return True

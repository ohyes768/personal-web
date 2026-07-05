"""定时清理：删 mtime > retention_days 的 markdown 文件。"""

import time
from pathlib import Path

from loguru import logger


def cleanup_old_posts(posts_dir: Path, retention_days: int = 15) -> int:
    """删除 mtime 超过 retention_days 天的 *.md，返回删除数。

    用 mtime 而非 front matter.created_at：mtime 是文件系统原生属性，
    读取成本低、无需解析文件内容。文件落地时 write_text 会刷新 mtime。
    """
    if not posts_dir.exists():
        return 0

    cutoff = time.time() - retention_days * 86400
    deleted = 0
    for f in posts_dir.glob("*.md"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                deleted += 1
        except Exception as e:
            logger.warning(f"清理失败 {f}: {e}")

    if deleted:
        logger.info(f"清理完成：删除 {deleted} 个过期文件（>{retention_days}d）")
    return deleted

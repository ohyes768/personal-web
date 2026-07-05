"""FastAPI 服务主入口。

启动方式：
    uvicorn src.main:app --host 0.0.0.0 --port 8095 --reload
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .endpoints import router, set_storage_config, set_rss_config, set_rss_token
from .cleanup import cleanup_old_posts


load_dotenv()


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


config = load_config("config/app.yaml")
app_config = config.get("app", {})

# 配置 logger（简化版，只输出到 stdout）
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    level=os.getenv("LOG_LEVEL", app_config.get("logging", {}).get("level", "INFO")),
    colorize=True,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：注入配置 → 启动清理 → 启动 scheduler"""
    storage = app_config.get("storage", {})
    posts_dir = Path(storage.get("posts_dir", "data/posts"))
    retention_days = int(storage.get("retention_days", 15))

    posts_dir.mkdir(parents=True, exist_ok=True)
    set_storage_config(posts_dir, retention_days)

    rss = app_config.get("rss", {})
    set_rss_config(
        channel_meta=rss.get("channel", {}),
        max_items=int(rss.get("max_items", 200)),
        default_limit=int(rss.get("default_limit", 50)),
    )

    # 注入 RSS token（仅环境变量，app.yaml 不写）
    set_rss_token(os.getenv("RSS_RELAY_TOKEN", ""))
    if not os.getenv("RSS_RELAY_TOKEN", ""):
        logger.warning("RSS_RELAY_TOKEN 未配置，所有 RSS 请求都会被拒绝")
    else:
        logger.info("RSS_RELAY_TOKEN 已加载")

    # 启动时清一次（清掉停机期间过期的）
    deleted = cleanup_old_posts(posts_dir, retention_days)
    logger.info(f"启动清理完成（删除 {deleted} 个 >{retention_days}d 文件）")

    # APScheduler 每天 03:00 跑清理
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        cleanup_old_posts,
        CronTrigger(hour=3, minute=3),  # 03:03，避开整点
        args=[posts_dir, retention_days],
        id="cleanup_old_posts",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler 已启动（每天 03:03 清理过期 post）")

    yield

    logger.info("关闭服务...")


server_config = app_config.get("server", {})
app = FastAPI(
    title="rss-relay",
    version="1.0.0",
    description="个人 RSS 中转：agent 推送 markdown，对外提供 RSS 2.0 feed",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=server_config.get("host", "0.0.0.0"),
        port=int(server_config.get("port", 8095)),
        reload=True,
    )

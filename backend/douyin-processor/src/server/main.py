"""
FastAPI 服务器
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from loguru import logger

from src.server.endpoints import (
    router,
    set_processor,
    set_rss_config,
    set_rss_token,
)
from src.scheduler import jobs as scheduler_jobs
from src.scheduler.manager import SchedulerManager
from src.scheduler.routes import router as scheduler_router
from src.processor.filesystem_client import FileSystemClient
from src.processor.asr_client import AliyunASRClient
from src.processor.status_manager import StatusManager
from src.processor.video_processor import VideoProcessor
from src.utils import load_config, setup_logger

# 加载 .env 文件
load_dotenv()

# 加载配置
config = load_config("config/app.yaml")

# 设置日志
log_config = config.get("app", {}).get("logging", {})
setup_logger(
    log_dir=log_config.get("dir", "logs"),
    level=log_config.get("level", "INFO")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("初始化视频处理器...")

    app_config = config.get("app", {})

    # 初始化各组件
    filesystem_config = app_config.get("filesystem", {})
    filesystem_client = FileSystemClient(
        base_url=filesystem_config.get("base_url", ""),
        query_endpoint=filesystem_config.get("query_endpoint", "/api/videos/query"),
        download_endpoint_template=filesystem_config.get("download_endpoint_template", "/api/videos/{id}/download"),
        timeout=filesystem_config.get("timeout", 300),
        cache_ttl=filesystem_config.get("cache_ttl", 30)
    )

    asr_config = app_config.get("asr", {})
    asr_client = AliyunASRClient(
        api_key=os.getenv(asr_config.get("access_key", ""), ""),
        model=asr_config.get("model", "fun-asr")
    )

    files_config = app_config.get("files", {})
    status_manager = StatusManager(
        status_file=files_config.get("status_file", "data/status.json")
    )

    video_processor = VideoProcessor(
        filesystem_client=filesystem_client,
        asr_client=asr_client,
        status_manager=status_manager,
        output_dir=files_config.get("output_dir", "data/output")
    )

    # 设置到全局
    set_processor(video_processor)
    app.state.processor = video_processor

    # 注入 RSS 配置（channel meta + limits）
    rss_config = app_config.get("rss", {})
    rss_channel = rss_config.get("channel", {})
    set_rss_config(
        channel_meta=rss_channel,
        max_items=rss_config.get("max_items", 200),
        default_limit=rss_config.get("default_limit", 50),
    )

    # 注入 RSS token（仅环境变量，app.yaml 不写）
    set_rss_token(os.getenv("DOUYIN_RSS_TOKEN", ""))

    logger.info("视频处理器初始化完成")

    # 启动定时清理 scheduler
    cleanup_config = app_config.get("cleanup", {})
    cleanup_days = int(cleanup_config.get("days", 45))
    cleanup_cron = cleanup_config.get("cron", "7 3 * * *")
    cleanup_tz = cleanup_config.get("timezone", "Asia/Shanghai")

    # 启动时立即清理一次(清停机期间过期的,失败不阻塞启动；不写 scheduler 历史)
    try:
        await scheduler_jobs.run_cleanup(
            {"processor": video_processor, "cleanup_days": cleanup_days},
            "cleanup_old_records",
            "startup",
        )
    except Exception as e:
        logger.error(f"启动时清理失败(非阻塞): {e}")

    # 内建调度管理器：process_pending(09:45/17:15) + cleanup(03:07)，
    # 取代裸 APScheduler 注册；页面可启停/立即执行/看历史（/api/scheduler/*）
    # cron 来源 app.yaml（host 只读挂载），enabled 持久化到 data/scheduler/enabled.json
    scheduler = SchedulerManager(
        app_config=app_config,
        data_dir=Path("data"),
        services={"processor": video_processor, "cleanup_days": cleanup_days},
    )
    scheduler.start()
    logger.info(
        f"APScheduler 已启动:每天 {cleanup_cron} ({cleanup_tz}) 清理 >{cleanup_days}d 过期记录；"
        f"process_pending 自动处理 status=pending 视频（cron 见上方注册日志）"
    )
    app.state.scheduler = scheduler

    yield

    # 关闭时清理
    logger.info("关闭 scheduler...")
    await app.state.scheduler.shutdown()
    logger.info("清理资源...")


# 创建 FastAPI 应用
server_config = config.get("app", {}).get("server", {})
app = FastAPI(
    title="douyin-processor",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)
# scheduler 管理 API（最终路径 /api/scheduler/*）
app.include_router(scheduler_router)


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "douyin-processor",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn

    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8093)

    uvicorn.run(
        "src.server.main:app",
        host=host,
        port=port,
        log_level="info"
    )

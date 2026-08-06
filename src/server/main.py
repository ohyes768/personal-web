"""
FastAPI 服务器
"""

import os
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from loguru import logger

from src.server.endpoints import (
    router,
    set_processor,
    set_rss_config,
    set_rss_token,
    _run_process_pending,
)
from src.processor.filesystem_client import FileSystemClient
from src.processor.asr_client import AliyunASRClient
from src.processor.status_manager import StatusManager
from src.processor.video_processor import VideoProcessor
from src.utils import load_config, setup_logger


async def _scheduled_cleanup(processor: "VideoProcessor", days: int) -> None:
    """定时清理任务:复用 status_manager + filesystem_client,与手动 API 同源。

    Args:
        processor: 已初始化的 VideoProcessor 实例(lifespan 启动后可用)
        days: 清理阈值(天)
    """
    try:
        deleted_ids = await processor.status_manager.cleanup_old_records(days)
        if not deleted_ids:
            logger.info(f"定时清理:无过期记录(>{days}d)")
            return
        success = 0
        failed = []
        for aid in deleted_ids:
            audio_filename = f"{aid}.wav"
            ok = await processor.filesystem_client.delete_file(audio_filename)
            if ok:
                success += 1
            else:
                failed.append(audio_filename)
            # 同步清 output json (data/output/{aweme_id}.json)，与 status.json 保持一致
            try:
                (processor.output_dir / f"{aid}.json").unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"清 output json 失败 {aid}: {e}")
        logger.info(
            f"定时清理完成:删 {success}/{len(deleted_ids)} 个文件(>{days}d),失败 {failed}"
        )
    except Exception as e:
        logger.error(f"定时清理失败: {e}")

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

    # 启动时立即清理一次(清停机期间过期的,失败不阻塞启动)
    try:
        await _scheduled_cleanup(video_processor, cleanup_days)
    except Exception as e:
        logger.error(f"启动时清理失败(非阻塞): {e}")

    scheduler = AsyncIOScheduler(timezone=cleanup_tz)
    scheduler.add_job(
        _scheduled_cleanup,
        CronTrigger.from_crontab(cleanup_cron, timezone=cleanup_tz),
        args=[video_processor, cleanup_days],
        id="cleanup_old_records",
        replace_existing=True,
    )

    # 注册 process_pending 自调度（09:45 / 17:15 北京时间，取代 n8n 外部触发）
    # 与 cleanup 共用同一个 scheduler，共用 endpoints._process_lock 自动防重入
    process_pending_config = app_config.get("process_pending", {})
    pp_tz = process_pending_config.get("timezone", cleanup_tz)
    pp_morning = process_pending_config.get("cron_morning", "45 9 * * *")
    pp_evening = process_pending_config.get("cron_evening", "15 17 * * *")
    scheduler.add_job(
        _run_process_pending,
        CronTrigger.from_crontab(pp_morning, timezone=pp_tz),
        id="process_pending_morning",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_process_pending,
        CronTrigger.from_crontab(pp_evening, timezone=pp_tz),
        id="process_pending_evening",
        replace_existing=True,
    )
    logger.info(
        f"APScheduler 已注册 process_pending: {pp_morning} / {pp_evening} ({pp_tz}) "
        f"自动处理 status=pending 视频"
    )

    scheduler.start()
    logger.info(
        f"APScheduler 已启动:每天 {cleanup_cron} ({cleanup_tz}) 清理 >{cleanup_days}d 过期记录"
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

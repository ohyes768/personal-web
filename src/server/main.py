"""
FastAPI 服务器
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from loguru import logger

from src.server.endpoints import router, set_processor, set_rss_config, set_rss_token
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

    yield

    # 关闭时清理
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

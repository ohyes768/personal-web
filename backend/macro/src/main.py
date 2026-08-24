"""FastAPI 应用主入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from src.api.routes import router
from src.utils.logger import setup_logger
from src.config import get_settings
from src import __version__

logger = setup_logger("main")
settings = get_settings()

# 创建 FastAPI 应用
app = FastAPI(
    title="Global Macro Finance API",
    description="全球宏观经济债券利率数据服务",
    version=__version__,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# gzip 压缩：/api/data 全量 JSON 几 MB，压缩率 ~90%。
# add 在 CORS 之后 = 外层包裹，让响应先经 CORS 头加好再压缩。
# minimum_size=1024 避免压缩小响应得不偿失（nginx gzip_min_length 也是 1024，两端对齐）。
app.add_middleware(GZipMiddleware, minimum_size=1024)

# 注册路由
app.include_router(router)

# 启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logger.info("=" * 50)
    logger.info("Global Macro Finance API 启动中...")
    logger.info(f"版本: {__version__}")
    logger.info(f"数据目录: {settings.data_dir}")
    logger.info("=" * 50)


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    logger.info("Global Macro Finance API 已关闭")


# 根路径
@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "macro",
        "version": __version__,
        "status": "running",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=True,
    )

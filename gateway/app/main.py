"""
API Gateway 主应用
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import economic, news, douyin, health
import logging

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="统一网关，聚合经济数据、新闻分析、抖音视频等服务",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由（转发到后端服务）
app.include_router(economic.router, prefix="/api/economic", tags=["经济数据"])
app.include_router(news.router, prefix="/api/news", tags=["新闻分析"])
app.include_router(douyin.router, prefix="/api/douyin", tags=["抖音视频"])
app.include_router(health.router, prefix="/api", tags=["健康检查"])


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    logger.info(f"📡 经济服务: {settings.FINANCIAL_SERVICE_URL}")
    logger.info(f"📰 新闻服务: {settings.NEWS_SERVICE_URL}")
    logger.info(f"🎥 抖音服务: {settings.DOUYIN_SERVICE_URL}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info(f"👋 {settings.APP_NAME} 关闭中...")


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )

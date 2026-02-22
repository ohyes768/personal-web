"""
健康检查路由
"""
from fastapi import APIRouter
from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "healthy",
        "services": {
            "financial": settings.FINANCIAL_SERVICE_URL,
            "news": settings.NEWS_SERVICE_URL,
            "douyin": settings.DOUYIN_SERVICE_URL
        }
    }

"""
新闻分析路由转发器
"""
from fastapi import APIRouter, Query, Request
from app.utils.http_client import proxy_request
from app.config import settings

router = APIRouter()


@router.get("/policy-ranking")
async def get_policy_ranking(
    request: Request,
    time_range: str = Query("1M", description="时间范围"),
    top_n: int = Query(20, description="返回数量")
):
    """转发到 xwlb-analyze 服务 - 获取政策推荐指数排行榜"""
    target_url = f"{settings.NEWS_SERVICE_URL}/api/news/policy-ranking"
    params = {"time_range": time_range, "top_n": top_n}
    return await proxy_request("GET", target_url, params=params, headers=dict(request.headers))


@router.get("/sector-impact/{date}")
async def get_sector_impact(request: Request, date: str):
    """转发到 xwlb-analyze 服务 - 获取板块影响数据"""
    target_url = f"{settings.NEWS_SERVICE_URL}/api/news/sector-impact/{date}"
    return await proxy_request("GET", target_url, headers=dict(request.headers))


@router.get("/sentiment-distribution")
async def get_sentiment_distribution(
    request: Request,
    time_range: str = Query("1M", description="时间范围")
):
    """转发到 xwlb-analyze 服务 - 获取情感分布数据"""
    target_url = f"{settings.NEWS_SERVICE_URL}/api/news/sentiment-distribution"
    params = {"time_range": time_range}
    return await proxy_request("GET", target_url, params=params, headers=dict(request.headers))


@router.get("/heatmap")
async def get_heatmap(
    request: Request,
    board_code: str = Query(..., description="板块代码"),
    time_range: str = Query("1M", description="时间范围")
):
    """转发到 xwlb-analyze 服务 - 获取板块热力图数据"""
    target_url = f"{settings.NEWS_SERVICE_URL}/api/news/heatmap"
    params = {"board_code": board_code, "time_range": time_range}
    return await proxy_request("GET", target_url, params=params, headers=dict(request.headers))

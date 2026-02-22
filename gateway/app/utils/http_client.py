"""
HTTP 客户端工具
用于代理请求到后端服务
"""
import httpx
from typing import Optional, Dict, Any
from app.config import settings
import logging

logger = logging.getLogger(__name__)


async def proxy_request(
    method: str,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: float = None
) -> Dict[str, Any]:
    """
    代理请求到后端服务

    Args:
        method: HTTP 方法 (GET, POST, PUT, DELETE)
        url: 目标 URL
        params: 查询参数
        headers: 请求头
        json: JSON 请求体
        timeout: 超时时间（秒）

    Returns:
        响应 JSON 数据
    """
    if timeout is None:
        timeout = settings.REQUEST_TIMEOUT

    # 过滤敏感的请求头
    filtered_headers = {}
    if headers:
        for key, value in headers.items():
            if key.lower() not in ['host', 'content-length', 'transfer-encoding']:
                filtered_headers[key] = value

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if method.upper() == "GET":
                response = await client.get(url, params=params, headers=filtered_headers)
            elif method.upper() == "POST":
                response = await client.post(url, json=json, headers=filtered_headers)
            elif method.upper() == "PUT":
                response = await client.put(url, json=json, headers=filtered_headers)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=filtered_headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json()

        except httpx.TimeoutException as e:
            logger.error(f"请求超时: {url} - {str(e)}")
            return {"success": False, "error": "请求超时", "detail": str(e)}
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP 错误: {url} - Status: {e.response.status_code}")
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}",
                "detail": str(e)
            }
        except httpx.HTTPError as e:
            logger.error(f"HTTP 错误: {url} - {str(e)}")
            return {"success": False, "error": "HTTP 请求失败", "detail": str(e)}
        except Exception as e:
            logger.error(f"未知错误: {url} - {str(e)}")
            return {"success": False, "error": "未知错误", "detail": str(e)}

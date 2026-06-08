"""
file-system-go 客户端
负责从 file-system-go 获取视频列表、下载/删除文件
（v2.0 起 file-system-go 简化为 5 个纯文件 CRUD 端点）
"""

import asyncio
import time
from pathlib import Path
from typing import Optional, List
from loguru import logger
import httpx

from src.models import VideoFile


class FileSystemClient:
    """file-system-go 客户端"""

    def __init__(
        self,
        base_url: str,
        query_endpoint: str = "/api/files/query",
        download_endpoint_template: str = "/api/files/{id}/download",
        delete_endpoint_template: str = "/api/files/{id}",
        timeout: int = 300,
        cache_ttl: int = 30
    ):
        """初始化客户端

        Args:
            base_url: file-system-go 基础 URL
            query_endpoint: 查询接口路径
            download_endpoint_template: 下载接口路径模板
            delete_endpoint_template: 删除接口路径模板
            timeout: 请求超时时间（秒）
            cache_ttl: 缓存有效期（秒），默认 30 秒
        """
        self.base_url = base_url.rstrip("/")
        self.query_url = f"{base_url}{query_endpoint}"
        self.download_endpoint_template = download_endpoint_template
        self.delete_endpoint_template = delete_endpoint_template
        self.timeout = timeout
        self.cache_ttl = cache_ttl

        # 视频列表缓存
        self._video_list_cache: Optional[List[VideoFile]] = None
        self._video_list_cache_time: float = 0

        logger.info(f"file-system-go 客户端初始化完成: {base_url}")

    async def get_video_list(
        self,
        filters: dict = None,
        use_cache: bool = True
    ) -> List[VideoFile]:
        """获取视频列表

        Args:
            filters: 过滤条件，如 {"prefix": "audio", "suffix": ".mp4"}
            use_cache: 是否使用缓存，默认 True

        Returns:
            视频文件列表
        """
        # 检查缓存是否有效
        current_time = time.time()
        if (use_cache and
            self._video_list_cache is not None and
            current_time - self._video_list_cache_time < self.cache_ttl):
            logger.info(f"返回缓存的视频列表（{len(self._video_list_cache)} 个）")
            return self._video_list_cache.copy()

        logger.info("获取视频列表")

        # 构建请求体，符合 file-system-go 的格式
        request_body = {}
        if filters:
            request_body["filters"] = filters

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.query_url,
                    json=request_body
                )

                if response.status_code == 200:
                    data = response.json()

                    # 检查 success 字段
                    if not data.get("success", False):
                        logger.error(f"获取视频列表失败: {data.get('error', 'Unknown error')}")
                        return []

                    videos = []

                    for item in data.get("videos", []):
                        # 从文件名提取 aweme_id（格式为 xxx.wav）
                        filename = item.get("filename", "")
                        aweme_id = filename.replace(".wav", "")

                        # 获取 URL，如果是相对路径则拼接 base_url
                        url = item.get("url", "")
                        if url and not url.startswith("http"):
                            url = f"{self.base_url}{url}"

                        videos.append(VideoFile(
                            aweme_id=aweme_id,
                            filename=filename,
                            size=item.get("size", 0),
                            url=url
                        ))

                    # 更新缓存
                    self._video_list_cache = videos
                    self._video_list_cache_time = current_time

                    logger.info(f"获取到 {len(videos)} 个视频")
                    return videos
                else:
                    logger.error(
                        f"获取视频列表失败: HTTP {response.status_code}, "
                        f"{response.text}"
                    )
                    return []

        except Exception as e:
            logger.error(f"获取视频列表异常: {e}")
            return []

    async def download_video(
        self,
        aweme_id: str,
        output_dir: str
    ) -> Optional[str]:
        """下载视频文件

        Args:
            aweme_id: 视频 ID
            output_dir: 输出目录

        Returns:
            下载的文件路径，失败返回 None
        """
        # v2.0: /api/files/{aweme_id}.wav/download
        filename = f"{aweme_id}.wav"
        download_url = f"{self.base_url}/api/files/{filename}/download"
        output_path = Path(output_dir) / filename

        logger.info(f"下载视频: {aweme_id} -> {output_path}")

        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(download_url)

                if response.status_code == 200:
                    # 保存文件
                    with open(output_path, "wb") as f:
                        f.write(response.content)

                    file_size = output_path.stat().st_size
                    logger.info(
                        f"视频下载成功: {output_path} "
                        f"({file_size / 1024 / 1024:.2f} MB)"
                    )
                    return str(output_path)
                else:
                    logger.error(
                        f"视频下载失败: HTTP {response.status_code}, "
                        f"{response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"视频下载异常: {e}")
            return None

    def invalidate_video_list_cache(self):
        """清除视频列表缓存"""
        self._video_list_cache = None
        self._video_list_cache_time = 0
        logger.info("视频列表缓存已清除")

    async def delete_file(self, audio_filename: str) -> bool:
        """删除 file-system-go 上的文件

        Args:
            audio_filename: 完整文件名（含扩展名），如 "123456789.wav"

        Returns:
            删除成功返回 True
        """
        # v2.0: /api/files/{filename} DELETE
        delete_url = f"{self.base_url}/api/files/{audio_filename}"

        logger.info(f"删除文件: {audio_filename}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(delete_url)

                if response.status_code == 200:
                    logger.info(f"文件删除成功: {audio_filename}")
                    return True
                else:
                    logger.error(
                        f"文件删除失败: HTTP {response.status_code}, "
                        f"{response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"文件删除异常: {e}")
            return False

    async def delete_video(self, aweme_id: str) -> bool:
        """删除视频（保留旧接口，调用 delete_file）"""
        return await self.delete_file(f"{aweme_id}.wav")

"""
本地共享目录音频存储（2026-11-25 v3）

取代 FileSystemClient（file-system-go HTTP 客户端）。
collector 与 douyin-backend 容器挂载同一宿主目录（~/douyin-audio），
音频文件直接以 {aweme_id}.wav 形式交接。

保持与 FileSystemClient 相同的外部接口：
- get_video_list() -> List[VideoFile]
- download_video(aweme_id, output_dir) -> 本地路径（共享目录下直接返回原路径的拷贝语义，
  LocalFunASRClient 需要"可读的本地文件"，这里直接复制到目标目录，保持临时目录可整体清理）
- delete_file(filename) -> bool
- invalidate_video_list_cache()（兼容旧调用，现为空操作）
"""

import asyncio
import shutil
from pathlib import Path
from typing import List, Optional

import httpx
from loguru import logger

from src.models import VideoFile


class LocalAudioStore:
    """共享目录音频存储"""

    def __init__(self, audio_dir: str, base_url: str = ""):
        """初始化

        Args:
            audio_dir: 共享音频目录（容器内路径）
            base_url: 兼容参数，未使用（旧接口签名）
        """
        self.audio_dir = Path(audio_dir)
        self.base_url = base_url  # 兼容保留

        if not self.audio_dir.exists():
            logger.warning(f"共享音频目录不存在: {self.audio_dir}（等待挂载或首次写入）")

        logger.info(f"本地音频存储初始化完成: {self.audio_dir}")

    def _wav_path(self, aweme_id: str) -> Path:
        return self.audio_dir / f"{aweme_id}.wav"

    async def get_video_list(
        self,
        filters: dict = None,
        use_cache: bool = True
    ) -> List[VideoFile]:
        """列出共享目录下所有 WAV（扫描目录，无缓存）

        Args:
            filters: 兼容参数，仅支持 {"suffix": ".wav"}
            use_cache: 兼容参数，未使用

        Returns:
            VideoFile 列表（url 字段填文件路径，供旧代码拼接展示）
        """
        suffix = ".wav"
        if filters and "suffix" in filters:
            suffix = filters["suffix"]

        try:
            files = sorted(
                p for p in self.audio_dir.glob(f"*{suffix}") if p.is_file()
            )
        except OSError as e:
            logger.error(f"扫描共享目录失败: {e}")
            return []

        result: List[VideoFile] = []
        for p in files:
            aweme_id = p.stem
            result.append(VideoFile(
                aweme_id=aweme_id,
                filename=p.name,
                url=str(p),          # 本地路径（旧代码用它定位音频）
                size=p.stat().st_size,
            ))
        return result

    async def download_video(
        self,
        aweme_id: str,
        output_dir: str
    ) -> Optional[str]:
        """取音频到目标目录（本地文件，复制一份以保持 tmp 目录可整体清理的语义）

        Args:
            aweme_id: 视频 ID
            output_dir: 输出目录

        Returns:
            文件路径，失败返回 None
        """
        src = self._wav_path(aweme_id)
        if not src.exists():
            logger.warning(f"音频不存在: {src}")
            return None

        output_path = Path(output_dir) / src.name
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # to_thread：避免大文件复制阻塞事件循环
            await asyncio.to_thread(shutil.copyfile, src, output_path)
            logger.info(f"音频就绪: {output_path} ({output_path.stat().st_size / 1024 / 1024:.2f} MB)")
            return str(output_path)
        except OSError as e:
            logger.error(f"复制音频失败: {src} -> {output_path}, {e}")
            return None

    async def delete_file(self, filename: str) -> bool:
        """删除共享目录下的音频文件

        Args:
            filename: 文件名（如 7382749187324987.wav）

        Returns:
            是否成功
        """
        path = self.audio_dir / filename
        try:
            if path.exists():
                path.unlink()
                logger.info(f"已删除音频: {filename}")
            return True
        except OSError as e:
            logger.error(f"删除音频失败: {filename}, {e}")
            return False

    def invalidate_video_list_cache(self):
        """兼容旧接口（本地扫描无缓存，空操作）"""
        pass

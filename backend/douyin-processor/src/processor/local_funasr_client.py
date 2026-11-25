"""
本地 FunASR ASR 客户端
调用 NAS 本机部署的 FunASR 容器（SenseVoiceSmall，http://funasr-asr:8000/asr）

与 AliyunASRClient 保持相同接口：transcribe_file() -> TranscriptResult
流程差异：阿里版直接传 URL 给云端；本地版需要先把音频下载到临时文件再上传。

注意：SenseVoiceSmall 只返回纯文本，无分段时间戳/置信度，
segments 恒为单段（0 ~ audio_duration），confidence 恒 1.0（占位）。
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

from src.models import TranscriptResult, TranscriptSegment


class LocalFunASRClient:
    """本地 FunASR 容器 ASR 客户端"""

    def __init__(
        self,
        base_url: str = "http://funasr-asr:8000",
        filesystem_client=None,
        timeout: int = 600,
    ):
        """初始化客户端

        Args:
            base_url: FunASR 服务地址（容器网络内）
            filesystem_client: FileSystemClient 实例，用于下载音频到临时文件
            timeout: ASR 请求超时（CPU 推理较慢，长音频需要宽松超时）
        """
        self.base_url = base_url.rstrip("/")
        self.asr_url = f"{self.base_url}/asr"
        self.filesystem_client = filesystem_client
        self.timeout = timeout

        if self.filesystem_client is None:
            logger.warning("LocalFunASRClient 未配置 filesystem_client，无法下载音频")

        logger.info(f"本地 FunASR ASR 客户端初始化完成: {self.asr_url}")

    async def transcribe_file(
        self,
        audio_file: str,
        file_url: str,
        format: str = "wav"
    ) -> Optional[TranscriptResult]:
        """识别音频文件

        Args:
            audio_file: 本地文件路径（未使用，兼容旧接口签名）
            file_url: 音频文件的公网 URL（用于提取 aweme_id 并经
                      FileSystemClient 从 file-system-go 下载）
            format: 音频格式

        Returns:
            转写结果对象，失败返回 None
        """
        tmp_path: Optional[str] = None
        try:
            # 1. 从 file-system-go 下载音频到临时文件
            tmp_path = await self._download_audio_to_tmp(file_url)
            if not tmp_path:
                return None

            file_size = Path(tmp_path).stat().st_size
            logger.info(f"音频已下载到临时文件: {tmp_path} ({file_size / 1024 / 1024:.2f} MB)")

            # 2. 调本地 FunASR /asr（CPU 推理，长音频耗时可观，放线程池避免阻塞事件循环）
            result = await asyncio.to_thread(self._post_asr, tmp_path)
            if result is None:
                return None

            text = result.get("text", "").strip()
            if not text:
                logger.info("ASR 识别结果为空（可能无解说）")
                return TranscriptResult(
                    text="",
                    segments=[],
                    confidence=0.0,
                    audio_duration=0.0,
                    has_transcript=False,
                )

            logger.info(f"识别完成: {len(text)} 字")

            # 3. SenseVoice 无时间戳，输出单段全文
            #    音频时长从 WAV 头估算（data 块大小 / (16000 * 2 bytes)）
            duration = self._estimate_wav_duration(tmp_path)
            return TranscriptResult(
                text=text,
                segments=[
                    TranscriptSegment(
                        start_time=0.0,
                        end_time=duration,
                        text=text,
                        confidence=1.0,
                    )
                ],
                confidence=1.0,
                audio_duration=duration,
            )

        except Exception as e:
            logger.error(f"本地 ASR 识别失败: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    async def _download_audio_to_tmp(self, file_url: str) -> Optional[str]:
        """从 file-system-go 下载音频到临时文件

        Args:
            file_url: 形如 https://host:1443/audio/{aweme_id}.wav 的 URL

        Returns:
            临时文件路径，失败返回 None
        """
        # 从 URL 提取 aweme_id（xxx/{aweme_id}.wav）
        filename = file_url.rstrip("/").split("/")[-1]

        if self.filesystem_client is not None:
            tmp_dir = tempfile.mkdtemp(prefix="asr_")
            path = await self.filesystem_client.download_video(
                aweme_id=filename.removesuffix(".wav"),
                output_dir=tmp_dir,
            )
            if path:
                return path
            logger.warning(f"共享目录取音频失败: {filename}")
            return None

        # 无 storage 客户端时，file_url 兼容为本地文件路径（v3 共享目录方案）
        if file_url.startswith("/") and Path(file_url).exists():
            return file_url

        logger.error(f"无法获取音频: {filename}（无存储客户端且非本地路径）")
        return None

    def _post_asr(self, audio_path: str) -> Optional[dict]:
        """同步调用 FunASR /asr

        Args:
            audio_path: 本地音频文件路径

        Returns:
            {"results": [...], "text": "..."} 或 None
        """
        try:
            with open(audio_path, "rb") as f:
                response = httpx.post(
                    self.asr_url,
                    files={"file": (Path(audio_path).name, f, "audio/wav")},
                    timeout=self.timeout,
                )

            if response.status_code != 200:
                logger.error(f"FunASR HTTP {response.status_code}: {response.text[:200]}")
                return None

            return response.json()

        except Exception as e:
            logger.error(f"FunASR 调用异常: {e}")
            return None

    @staticmethod
    def _estimate_wav_duration(wav_path: str) -> float:
        """从 WAV 文件估算时长（秒）

        假设 16kHz 16bit 单声道（collector 转码时的固定参数）。
        解析失败时返回 0.0。
        """
        try:
            import wave
            with wave.open(wav_path, "rb") as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                if rate <= 0:
                    return 0.0
                return frames / rate
        except Exception:
            return 0.0

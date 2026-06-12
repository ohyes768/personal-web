"""
ASR客户端
封装阿里云百炼平台 FunASR API 调用
"""

import asyncio
from pathlib import Path
from typing import Optional
from loguru import logger
import httpx

from src.models import TranscriptResult, TranscriptSegment


class AliyunASRClient:
    """阿里云百炼平台 ASR 客户端"""

    def __init__(self, api_key: str, model: str = "fun-asr"):
        """初始化ASR客户端

        Args:
            api_key: 百炼平台 API Key
            model: 模型名称
        """
        self.api_key = api_key
        self.model = model

        # API 端点
        self.submit_url = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
        self.query_url_template = "https://dashscope.aliyuncs.com/api/v1/tasks/{}"

        # 验证配置
        if not self.api_key:
            logger.warning("百炼平台 API Key 未配置，ASR 功能将不可用")

        logger.info("阿里云百炼平台 ASR 客户端初始化完成")

    async def transcribe_file(
        self,
        audio_file: str,
        file_url: str,
        format: str = "wav"
    ) -> Optional[TranscriptResult]:
        """识别音频文件

        Args:
            audio_file: 音频文件路径（可选，仅用于日志）
            file_url: 音频文件的公网 URL
            format: 音频格式

        Returns:
            转写结果对象，失败返回 None
        """
        logger.info(f"开始识别音频: {file_url}")

        # 如果传入了本地文件路径，检查是否存在（可选）
        if audio_file:
            audio_path = Path(audio_file)
            if not audio_path.exists():
                logger.warning(f"本地音频文件不存在: {audio_file}，但将继续使用 URL 进行识别")

        try:
            # 提交 ASR 任务
            task_id = await self._submit_task([file_url])

            if not task_id:
                logger.error("提交 ASR 任务失败")
                return None

            logger.info(f"ASR 任务已提交，任务 ID: {task_id}")

            # 轮询查询结果
            result = await self._wait_for_result(task_id)

            if result is None:
                logger.error(f"识别任务失败或超时: {task_id}")
                return None

            # ASR 跑完但无文字内容
            if isinstance(result, dict) and not result.get("has_transcript", True):
                logger.info(f"ASR 无解说: {task_id}")
                return TranscriptResult(
                    text="",
                    segments=[],
                    confidence=0.0,
                    audio_duration=0.0,
                    has_transcript=False,
                )

            logger.info(f"识别任务完成: {task_id}")
            return self._parse_response(result)

        except Exception as e:
            logger.error(f"音频识别失败: {e}")
            return None

    def _parse_response(
        self,
        response: dict
    ) -> TranscriptResult:
        """解析API响应

        Args:
            response: API返回的原始数据

        Returns:
            标准化的转写结果
        """
        # 百炼平台 ASR 的响应格式
        results = response.get("results", [])

        if not results:
            logger.warning("识别结果为空")
            return TranscriptResult(
                text="",
                segments=[],
                confidence=0.0,
                audio_duration=0.0
            )

        # 获取第一个结果（通常只提交一个文件）
        first_result = results[0]
        transcription_url = first_result.get("transcription_url", "")

        if not transcription_url:
            logger.warning("未获取到转写结果 URL")
            return TranscriptResult(
                text="",
                segments=[],
                confidence=0.0,
                audio_duration=0.0
            )

        # 下载转写结果
        try:
            result_data = self._fetch_transcription_result(transcription_url)
            return self._parse_transcription_data(result_data)
        except Exception as e:
            logger.error(f"解析转写结果失败: {e}")
            return TranscriptResult(
                text="",
                segments=[],
                confidence=0.0,
                audio_duration=0.0
            )

    def _fetch_transcription_result(self, url: str) -> dict:
        """获取转写结果

        Args:
            url: 转写结果的 URL

        Returns:
            转写结果数据
        """
        # 使用同步 HTTP 请求获取结果
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        return response.json()

    def _parse_transcription_data(self, data: dict) -> TranscriptResult:
        """解析转写数据

        Args:
            data: 转写结果数据

        Returns:
            标准化的转写结果
        """
        transcripts = data.get("transcripts", [])

        if not transcripts:
            return TranscriptResult(
                text="",
                segments=[],
                confidence=0.0,
                audio_duration=0.0
            )

        # 获取第一个音轨
        first_transcript = transcripts[0]
        sentences = first_transcript.get("sentences", [])

        # 构建完整文本
        full_text = first_transcript.get("text", "")

        # 构建分段信息
        segments = []
        for sentence in sentences:
            words = sentence.get("words", [])
            # 计算平均置信度
            confidence = 0.0
            if words:
                confidence = sum(
                    w.get("punctuation_probability", 0.5)
                    for w in words
                ) / len(words)

            segments.append(TranscriptSegment(
                start_time=sentence.get("begin_time", 0) / 1000.0,  # 转换为秒
                end_time=sentence.get("end_time", 0) / 1000.0,      # 转换为秒
                text=sentence.get("text", ""),
                confidence=confidence
            ))

        # 获取音频时长
        properties = data.get("properties", {})
        audio_duration = properties.get("original_duration_in_milliseconds", 0) / 1000.0

        # 计算整体置信度
        confidence = 0.0
        if segments:
            confidence = sum(seg.confidence for seg in segments) / len(segments)

        return TranscriptResult(
            text=full_text,
            segments=segments,
            confidence=confidence,
            audio_duration=audio_duration
        )

    async def _submit_task(self, file_urls: list[str]) -> Optional[str]:
        """提交 ASR 任务

        Args:
            file_urls: 文件 URL 列表

        Returns:
            任务 ID，失败返回 None
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable"
        }

        data = {
            "model": self.model,
            "input": {
                "file_urls": file_urls
            },
            "parameters": {
                "channel_id": [0]
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.submit_url,
                    headers=headers,
                    json=data
                )

                if response.status_code == 200:
                    result = response.json()
                    task_id = result.get("output", {}).get("task_id")

                    if task_id:
                        return task_id
                    else:
                        logger.error(f"提交任务失败: {result}")
                        return None
                else:
                    logger.error(
                        f"提交任务失败: HTTP {response.status_code}, "
                        f"{response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"提交任务异常: {e}")
            return None

    async def _wait_for_result(
        self,
        task_id: str,
        max_wait: int = 300,
        interval: int = 2
    ) -> Optional[dict]:
        """等待任务完成

        Args:
            task_id: 任务 ID
            max_wait: 最大等待时间（秒）
            interval: 查询间隔（秒）

        Returns:
            任务结果，失败或超时返回 None
        """
        query_url = self.query_url_template.format(task_id)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        wait_time = 0

        while wait_time < max_wait:
            await asyncio.sleep(interval)
            wait_time += interval

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        query_url,
                        headers=headers
                    )

                    if response.status_code == 200:
                        result = response.json()
                        output = result.get("output", {})
                        task_status = output.get("task_status")

                        if task_status == "SUCCEEDED":
                            return output
                        elif task_status == "FAILED":
                            error_code = output.get("code", "")
                            if error_code == "ASR_RESPONSE_HAVE_NO_WORDS":
                                # ASR 成功跑完但无文字内容，不算失败
                                logger.warning(f"ASR 识别无文字内容: {task_id}")
                                return {"has_transcript": False}
                            logger.error(f"任务失败: {output}")
                            return None
                        else:
                            logger.debug(f"任务状态: {task_status}, 已等待 {wait_time} 秒")
                    else:
                        logger.error(f"查询任务失败: HTTP {response.status_code}")
                        return None

            except Exception as e:
                logger.error(f"查询任务异常: {e}")
                return None

        logger.error(f"任务超时（{max_wait} 秒）")
        return None

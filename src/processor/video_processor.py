"""
音频处理器
协调整个音频处理流程：获取音频列表、ASR识别、保存结果
"""

import time
from pathlib import Path
from loguru import logger

from src.models import TranscriptResult, ProcessResult
from src.processor.filesystem_client import FileSystemClient
from src.processor.asr_client import AliyunASRClient
from src.processor.status_manager import StatusManager
from src.utils import save_json


class VideoProcessor:
    """音频处理器"""

    def __init__(
        self,
        filesystem_client: FileSystemClient,
        asr_client: AliyunASRClient,
        status_manager: StatusManager,
        output_dir: str = "data/output"
    ):
        """初始化音频处理器

        Args:
            filesystem_client: file-system-go 客户端
            asr_client: ASR 客户端
            status_manager: 状态管理器
            output_dir: 输出目录
        """
        self.filesystem_client = filesystem_client
        self.asr_client = asr_client
        self.status_manager = status_manager
        self.output_dir = Path(output_dir)

        logger.info("音频处理器初始化完成")

    async def process_pending(self) -> dict:
        """处理所有 status=pending 的视频（v2.0 流程）

        从 status_manager.list_pending() 拉队列，逐个调阿里 ASR，
        成功 mark_processed（→ unread + 写 output），失败 mark_failed。

        Returns:
            处理结果统计 {total, success, failed}
        """
        logger.info("开始处理 pending 视频")

        pending_list = await self.status_manager.list_pending()
        if not pending_list:
            logger.warning("没有 pending 视频")
            return {"total": 0, "success": 0, "failed": 0}

        logger.info(f"找到 {len(pending_list)} 个 pending 视频")

        # 拉一次 file-system-go 列表，建 aweme_id → url 映射，避免每个视频重拉
        videos = await self.filesystem_client.get_video_list(
            filters={"suffix": ".wav"},
            use_cache=True,
        )
        url_map = {v.aweme_id: v.url for v in videos}

        total = len(pending_list)
        success = 0
        failed = 0

        for item in pending_list:
            aweme_id = item["aweme_id"]
            audio_url = url_map.get(aweme_id, "")

            if not audio_url:
                error = "找不到音频文件 URL"
                logger.warning(f"{aweme_id}: {error}")
                await self.status_manager.mark_failed(aweme_id, error)
                failed += 1
                continue

            start_time = time.time()
            logger.info(f"开始处理: {aweme_id} ({audio_url})")

            try:
                transcript = await self.asr_client.transcribe_file(
                    audio_file="",
                    file_url=audio_url,
                )

                if not transcript:
                    error = "ASR 识别失败"
                    logger.error(f"{aweme_id}: {error}")
                    await self.status_manager.mark_failed(aweme_id, error)
                    failed += 1
                    continue

                # 拼 output 数据，metadata 直接从 pending 记录取（不依赖已删除的 get_video_metadata）
                output_data = {
                    "aweme_id": aweme_id,
                    "text": transcript.text,
                    "segments": [
                        {
                            "start_time": seg.start_time,
                            "end_time": seg.end_time,
                            "text": seg.text,
                            "confidence": seg.confidence,
                        }
                        for seg in transcript.segments
                    ],
                    "confidence": transcript.confidence,
                    "audio_duration": transcript.audio_duration,
                    "title": item.get("title", ""),
                    "author": item.get("author", ""),
                    "description": item.get("description", ""),
                    "video_publish_time": item.get("video_publish_time", ""),
                }

                await self.status_manager.mark_processed(aweme_id, transcript=output_data)
                success += 1

                cost = time.time() - start_time
                logger.info(f"处理成功: {aweme_id} (耗时 {cost:.2f}s)")

            except Exception as e:
                error = f"处理异常: {e}"
                logger.error(f"{aweme_id}: {error}")
                await self.status_manager.mark_failed(aweme_id, error)
                failed += 1

        summary = {
            "total": total,
            "success": success,
            "failed": failed,
        }
        logger.info(f"处理完成: 总计 {total}，成功 {success}，失败 {failed}")
        return summary

    async def process_all(self) -> dict:
        """处理所有音频（v1.0 旧流程，依赖已删除的 filesystem_client.get_video_metadata，
        目前已不可用，保留作历史参考）

        Returns:
            处理结果统计
        """
        logger.info("开始处理所有音频")

        # 获取音频列表（过滤 .wav 文件）
        videos = await self.filesystem_client.get_video_list(
            filters={"suffix": ".wav"}
        )

        if not videos:
            logger.warning("没有找到音频文件")
            return {
                "total": 0,
                "processed": 0,
                "success": 0,
                "failed": 0
            }

        logger.info(f"找到 {len(videos)} 个音频文件")

        # 统计结果
        total = len(videos)
        processed = 0
        success = 0
        failed = 0

        # 逐个处理音频
        for video in videos:
            # 检查是否已处理
            if await self.status_manager.is_completed(video.aweme_id):
                logger.info(f"音频已处理，跳过: {video.aweme_id}")
                processed += 1
                success += 1
                continue

            # 处理音频
            result = await self.process_audio(video)

            processed += 1
            if result.success:
                success += 1
            else:
                failed += 1

        summary = {
            "total": total,
            "processed": processed,
            "success": success,
            "failed": failed
        }

        logger.info(
            f"处理完成: 总计 {total} 个，"
            f"成功 {success} 个，"
            f"失败 {failed} 个"
        )

        return summary

    async def process_audio(self, video) -> ProcessResult:
        """处理单个音频

        Args:
            video: 音频信息

        Returns:
            处理结果
        """
        aweme_id = video.aweme_id
        start_time = time.time()

        logger.info(f"开始处理音频: {aweme_id}")

        try:
            # 标记为处理中
            await self.status_manager.mark_processing(aweme_id)

            # 直接使用 file-system-go 的公网 URL
            audio_url = video.url  # 如: http://your-ecs-ip:8000/audio/xxx.wav

            if not audio_url:
                error = "音频 URL 为空"
                await self.status_manager.mark_failed(aweme_id, error)
                return ProcessResult(
                    aweme_id=aweme_id,
                    success=False,
                    error_message=error
                )

            logger.info(f"音频 URL: {audio_url}")

            # ASR 识别（传入 URL 和虚拟的本地文件路径）
            transcript = await self.asr_client.transcribe_file(
                audio_file="",  # 不需要本地文件
                file_url=audio_url
            )

            # 保存结果
            if transcript:
                # 获取元数据（从 file-system-go）
                metadata = await self.filesystem_client.get_video_metadata(aweme_id)
                await self._save_result(aweme_id, transcript, metadata)
                await self.status_manager.mark_completed(aweme_id)

                process_time = time.time() - start_time
                logger.info(
                    f"音频处理成功: {aweme_id} "
                    f"(耗时 {process_time:.2f} 秒)"
                )

                return ProcessResult(
                    aweme_id=aweme_id,
                    success=True,
                    transcript=transcript,
                    process_time=process_time
                )
            else:
                error = "ASR 识别失败"
                await self.status_manager.mark_failed(aweme_id, error)
                return ProcessResult(
                    aweme_id=aweme_id,
                    success=False,
                    error_message=error
                )

        except Exception as e:
            error = f"处理异常: {e}"
            logger.error(f"音频处理失败: {aweme_id} - {error}")
            await self.status_manager.mark_failed(aweme_id, error)

            return ProcessResult(
                aweme_id=aweme_id,
                success=False,
                error_message=error
            )

    async def _save_result(
        self,
        aweme_id: str,
        transcript: TranscriptResult,
        metadata = None
    ):
        """保存识别结果

        Args:
            aweme_id: 视频 ID
            transcript: 识别结果
            metadata: 视频元数据（可选）
        """
        output_file = self.output_dir / f"{aweme_id}.json"

        # 构建输出数据
        output_data = {
            "aweme_id": aweme_id,
            "text": transcript.text,
            "segments": [
                {
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "text": seg.text,
                    "confidence": seg.confidence
                }
                for seg in transcript.segments
            ],
            "confidence": transcript.confidence,
            "audio_duration": transcript.audio_duration
        }

        # 添加元数据信息
        if metadata:
            output_data.update({
                "title": metadata.title,
                "author": metadata.author,
                "description": metadata.description,
                "upload_time": metadata.upload_time
            })

        # 保存为 JSON 文件
        save_json(output_data, str(output_file))

        logger.info(f"识别结果已保存: {output_file}")

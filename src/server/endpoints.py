"""
API 接口端点
"""

import asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
from loguru import logger

from src.utils import load_json

router = APIRouter()

# 全局处理器引用（在 main.py 中设置）
processor = None

# 处理任务锁：避免并发触发同一批 pending 被处理两次（重复消耗 ASR 配额）
_process_lock = asyncio.Lock()


def set_processor(proc):
    """设置处理器实例"""
    global processor
    processor = proc


class ProcessResponse(BaseModel):
    """处理响应"""
    success: bool
    message: str
    data: Optional[dict] = None


class ResultResponse(BaseModel):
    """结果响应"""
    success: bool
    data: Optional[dict] = None


class TaskResponse(BaseModel):
    """任务响应"""
    success: bool
    message: str
    data: Optional[dict] = None


# 新增响应模型
class TranscriptInfo(BaseModel):
    """转写信息"""
    text: str
    segments: Optional[List[dict]] = None
    confidence: float
    audio_duration: float


class VideoListItem(BaseModel):
    """视频列表项"""
    aweme_id: str
    status: str
    title: str
    author: str
    audio_url: str
    transcript: Optional[TranscriptInfo] = None
    processed_at: Optional[int] = None
    upload_time: Optional[str] = None
    is_read: bool = False
    read_at: Optional[int] = None


class VideoListResponse(BaseModel):
    """视频列表响应"""
    total_count: int
    videos: List[VideoListItem]
    page: int
    page_size: int


class VideoDetailResponse(BaseModel):
    """视频详情响应"""
    aweme_id: str
    status: str
    title: str
    author: str
    description: str
    audio_url: str
    transcript: Optional[TranscriptInfo] = None
    processed_at: Optional[int] = None
    upload_time: Optional[str] = None
    error: Optional[str] = None
    is_read: bool = False
    read_at: Optional[int] = None


class StatsResponse(BaseModel):
    """统计信息响应"""
    total: int
    completed: int
    processing: int
    failed: int
    pending: int
    success_rate: float


class MarkReadRequest(BaseModel):
    """标记已读请求"""
    is_read: bool


class ActionResponse(BaseModel):
    """操作响应"""
    success: bool
    message: str


async def _run_process_pending():
    """后台任务：拿锁 → 跑 process_pending → 释放锁"""
    async with _process_lock:
        try:
            await processor.process_pending()
        except Exception as e:
            logger.error(f"process_pending 后台任务异常: {e}")


@router.post("/api/process/pending", response_model=TaskResponse)
async def trigger_process_pending():
    """触发处理 status=pending 的视频（ASR → unread）

    行为：
      1. 检查锁：已有任务在跑 → 拒（success=false）
      2. 拉 pending 列表：空 → 直接返回
      3. 非空 → asyncio.create_task 后台串行处理，立即返回
    """
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    if _process_lock.locked():
        return TaskResponse(
            success=False,
            message="已有处理任务正在进行中，请稍后再试",
            data={"pending": 0},
        )

    pending_list = await processor.status_manager.list_pending()
    if not pending_list:
        return TaskResponse(
            success=True,
            message="没有待处理的音频",
            data={"pending": 0},
        )

    asyncio.create_task(_run_process_pending())

    logger.info(f"已启动 pending 处理任务: {len(pending_list)} 个视频")
    return TaskResponse(
        success=True,
        message=f"已启动 ASR 处理（后台串行运行 {len(pending_list)} 个视频）",
        data={"pending": len(pending_list)},
    )


@router.get("/api/aweme/{aweme_id}/status")
async def get_aweme_status(aweme_id: str) -> dict:
    """单个数据查询（douyin-collector 调，判断是否需要上传）

    替代旧的 /api/aweme/{id}/skip。返回 known/status/audio_filename，
    UI/前端也能用。
    """
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")
    return await processor.status_manager.get_status_detail(aweme_id)


class MarkPendingRequest(BaseModel):
    """追加待处理请求"""
    audio_filename: str
    title: str = ""
    author: str = ""
    description: str = ""


@router.post("/api/aweme/{aweme_id}/pending")
async def mark_aweme_pending(aweme_id: str, request: MarkPendingRequest) -> dict:
    """追加待处理（douyin-collector 上传后调）"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")
    try:
        await processor.status_manager.mark_pending(
            aweme_id=aweme_id,
            audio_filename=request.audio_filename,
            title=request.title,
            author=request.author,
            description=request.description,
        )
        return {"success": True, "message": "已加入待处理"}
    except Exception as e:
        logger.error(f"追加待处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/aweme/pending")
async def list_pending_aweme() -> dict:
    """拉待处理列表（process 处理脚本调）"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")
    items = await processor.status_manager.list_pending()
    return {"items": items}


class MarkProcessedRequest(BaseModel):
    """标记处理完请求（ASR 完成时调）"""
    transcript: Optional[dict] = None


@router.post("/api/aweme/{aweme_id}/processed")
async def mark_aweme_processed(aweme_id: str, request: MarkProcessedRequest) -> dict:
    """标记处理完（ASR 完成）→ 状态变 unread"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")
    try:
        await processor.status_manager.mark_processed(
            aweme_id=aweme_id,
            transcript=request.transcript,
        )
        return {"success": True, "message": "已标记为未读"}
    except Exception as e:
        logger.error(f"标记处理完失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/aweme/{aweme_id}/unread", response_model=ActionResponse)
async def mark_aweme_unread(aweme_id: str):
    """标回未读（用户撤回已读时用）"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")
    try:
        await processor.status_manager.mark_unread(aweme_id)
        return ActionResponse(success=True, message="已标记为未读")
    except Exception as e:
        logger.error(f"标记未读失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/aweme/cleanup")
async def cleanup_old_aweme(days: int = Query(30, ge=1, description="清理阈值（天）")):
    """清理过期记录（process 清理脚本调）

    行为：
      1. 找 status=unread/read 且 processed_at 超过 N 天的记录
      2. 调 file-system-go 删物理文件
      3. 从 status.json 硬删
    """
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")
    try:
        deleted_ids = await processor.status_manager.cleanup_old_records(days)
        failed = []
        success_count = 0
        for aid in deleted_ids:
            audio_filename = f"{aid}.wav"
            ok = await processor.filesystem_client.delete_file(audio_filename)
            if ok:
                success_count += 1
            else:
                failed.append(audio_filename)
        logger.info(f"cleanup: 删 {success_count}/{len(deleted_ids)} 个文件，失败 {len(failed)}")
        return {
            "success": True,
            "deleted": success_count,
            "failed": failed,
        }
    except Exception as e:
        logger.error(f"cleanup 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/videos/{aweme_id}/result", response_model=ResultResponse)
async def get_video_result(aweme_id: str):
    """获取视频处理结果"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info(f"查询视频结果: {aweme_id}")

    try:
        # 检查状态
        status = await processor.status_manager.get_status(aweme_id)

        if status is None:
            return ResultResponse(
                success=True,
                data={
                    "aweme_id": aweme_id,
                    "status": "pending",
                    "message": "视频尚未处理"
                }
            )

        if status == "processing":
            return ResultResponse(
                success=True,
                data={
                    "aweme_id": aweme_id,
                    "status": "processing",
                    "message": "视频正在处理中"
                }
            )

        if status == "failed":
            all_statuses = await processor.status_manager.get_all_statuses()
            error = all_statuses.get(aweme_id, {}).get("error", "未知错误")
            return ResultResponse(
                success=True,
                data={
                    "aweme_id": aweme_id,
                    "status": "failed",
                    "error": error
                }
            )

        # 已完成，读取结果文件
        result_file = Path(processor.output_dir) / f"{aweme_id}.json"

        if not result_file.exists():
            return ResultResponse(
                success=True,
                data={
                    "aweme_id": aweme_id,
                    "status": "completed",
                    "message": "结果文件不存在"
                }
            )

        result_data = load_json(str(result_file))
        result_data["status"] = "completed"

        return ResultResponse(
            success=True,
            data=result_data
        )

    except Exception as e:
        logger.error(f"查询结果失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/videos", response_model=VideoListResponse)
async def get_videos(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选: v2.0: unread/read/deleted/pending；兼容旧 completed/processing/failed"),
    is_read: Optional[bool] = Query(None, description="已读状态筛选（兼容旧字段，新流程以 status=read/unread 为准）")
):
    """获取视频列表（支持分页和状态筛选）

    v2.0 适配：
    - 已读/未读已并入 status 字段（read/unread），兼容旧 is_read 字段
    - 默认过滤掉 pending + deleted 状态
    """
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info(f"获取视频列表: page={page}, page_size={page_size}, status={status}, is_read={is_read}")

    try:
        # 获取所有视频（使用缓存）
        all_videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"},
            use_cache=True
        )

        # 获取所有状态
        all_statuses = await processor.status_manager.get_all_statuses()

        # 第一遍：快速筛选（只读内存数据）
        candidate_videos = []
        for video in all_videos:
            aweme_id = video.aweme_id
            status_data = all_statuses.get(aweme_id, {})
            video_status = status_data.get("status", "pending")
            # 兼容：v2.0 用 status 字段，旧数据有 is_read 字段
            # 优先从 status 字段推断（status=read → is_read=true）
            if video_status in ("read", "unread", "deleted"):
                video_is_read = (video_status == "read")
            else:
                video_is_read = status_data.get("is_read", False)

            # 默认过滤掉 pending 和 deleted 状态的视频
            if video_status in ("pending", "deleted"):
                continue

            # 状态筛选
            if status and video_status != status:
                continue

            # 已读状态筛选（兼容 is_read 入参）
            if is_read is not None and video_is_read != is_read:
                continue

            candidate_videos.append({
                "aweme_id": aweme_id,
                "status": video_status,
                "is_read": video_is_read,
                "audio_url": video.url,
                "status_data": status_data
            })

        # 按上传时间倒序排序（先读取 upload_time）
        for v in candidate_videos:
            aweme_id = v["aweme_id"]
            # 尝试从 output 文件读取 upload_time
            result_file = processor.output_dir / f"{aweme_id}.json"
            if result_file.exists():
                try:
                    result_data = load_json(str(result_file))
                    v["upload_time"] = result_data.get("upload_time", "")
                except:
                    v["upload_time"] = ""
            else:
                v["upload_time"] = ""

        # 分成两组：有时间的和没时间的
        with_time = [v for v in candidate_videos if v["upload_time"]]
        without_time = [v for v in candidate_videos if not v["upload_time"]]

        # 有时间的按时间倒序
        with_time.sort(key=lambda x: x["upload_time"], reverse=True)
        # 没时间的按 ID 倒序
        without_time.sort(key=lambda x: x["aweme_id"], reverse=True)

        # 合并
        candidate_videos = with_time + without_time

        # 分页处理
        total_count = len(candidate_videos)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_videos = candidate_videos[start_idx:end_idx]

        # 只读取当前页需要的文件数据
        video_list = []
        for v in page_videos:
            aweme_id = v["aweme_id"]
            video_status = v["status"]
            status_data = v["status_data"]

            # 默认值
            metadata = {"title": "", "author": "", "description": "", "upload_time": None}
            transcript = None
            processed_at = None
            read_at = None

            # 读取转写结果（仅已完成且有结果文件）
            if video_status == "completed":
                result_file = processor.output_dir / f"{aweme_id}.json"
                if result_file.exists():
                    result_data = load_json(str(result_file))

                    # 从结果文件获取 metadata（优先）
                    if result_data.get("title"):
                        metadata = {
                            "title": result_data.get("title", ""),
                            "author": result_data.get("author", ""),
                            "description": result_data.get("description", ""),
                            "upload_time": result_data.get("upload_time")
                        }

                    transcript = TranscriptInfo(
                        text=result_data.get("text", ""),
                        segments=result_data.get("segments"),
                        confidence=result_data.get("confidence", 0.0),
                        audio_duration=result_data.get("audio_duration", 0.0)
                    )

                    # 从状态文件获取处理时间
                    processed_at_str = status_data.get("updated_at", "")
                    if processed_at_str:
                        try:
                            processed_at = int(datetime.fromisoformat(processed_at_str).timestamp())
                        except:
                            pass

            # v2.0: metadata 只从 result_data 取（status.json 已闭环）
            # 原 v1.0 兜底（filesystem_client.get_video_metadata）已删

            # 获取已读时间
            read_at_str = status_data.get("read_at")
            if read_at_str:
                try:
                    read_at = int(datetime.fromisoformat(read_at_str).timestamp())
                except:
                    pass

            video_list.append(VideoListItem(
                aweme_id=aweme_id,
                status=video_status,
                title=metadata.get("title", ""),
                author=metadata.get("author", ""),
                audio_url=v["audio_url"],
                transcript=transcript,
                processed_at=processed_at,
                upload_time=metadata.get("upload_time"),
                is_read=v["is_read"],
                read_at=read_at
            ))

        return VideoListResponse(
            total_count=total_count,
            videos=video_list,
            page=page,
            page_size=page_size
        )

    except Exception as e:
        logger.error(f"获取视频列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/videos/{aweme_id}", response_model=VideoDetailResponse)
async def get_video_detail(aweme_id: str):
    """获取单个视频详情"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info(f"获取视频详情: {aweme_id}")

    try:
        # 获取状态
        status = await processor.status_manager.get_status(aweme_id)
        video_status = status if status else "pending"

        # 获取所有状态（用于获取详细信息和错误信息）
        all_statuses = await processor.status_manager.get_all_statuses()
        status_data = all_statuses.get(aweme_id, {})

        # 获取已读状态
        is_read = status_data.get("is_read", False)
        read_at = None
        read_at_str = status_data.get("read_at")
        if read_at_str:
            try:
                read_at = int(datetime.fromisoformat(read_at_str).timestamp())
            except:
                pass

        # 获取音频 URL（使用缓存）
        videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"},
            use_cache=True
        )
        audio_url = ""
        for video in videos:
            if video.aweme_id == aweme_id:
                audio_url = video.url
                break

        # 读取转写结果和 metadata（仅已完成）
        transcript = None
        processed_at = None
        error = None
        title = ""
        author = ""
        description = ""
        upload_time = None

        if video_status == "completed":
            result_file = processor.output_dir / f"{aweme_id}.json"
            if result_file.exists():
                result_data = load_json(str(result_file))
                transcript = TranscriptInfo(
                    text=result_data.get("text", ""),
                    segments=result_data.get("segments"),
                    confidence=result_data.get("confidence", 0.0),
                    audio_duration=result_data.get("audio_duration", 0.0)
                )
                # 从结果文件获取 metadata（优先）
                title = result_data.get("title", "")
                author = result_data.get("author", "")
                description = result_data.get("description", "")
                upload_time = result_data.get("upload_time")

                # 获取处理时间
                processed_at_str = status_data.get("updated_at", "")
                if processed_at_str:
                    try:
                        processed_at = int(datetime.fromisoformat(processed_at_str).timestamp())
                    except:
                        pass
        elif video_status == "failed":
            error = status_data.get("error", "未知错误")

        # v2.0: metadata 只从 result_data 取（status.json 已闭环）
        # 原 v1.0 兜底（filesystem_client.get_video_metadata）已删

        return VideoDetailResponse(
            aweme_id=aweme_id,
            status=video_status,
            title=title,
            author=author,
            description=description,
            audio_url=audio_url,
            transcript=transcript,
            processed_at=processed_at,
            upload_time=upload_time,
            error=error,
            is_read=is_read,
            read_at=read_at
        )

    except Exception as e:
        logger.error(f"获取视频详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """获取处理统计信息"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info("获取统计信息")

    try:
        # 从 file-system-go 获取所有视频列表（带缓存）
        all_videos = await processor.filesystem_client.get_video_list(
            filters={"suffix": ".wav"},
            use_cache=True
        )

        # 从 status_manager 获取所有状态
        all_statuses = await processor.status_manager.get_all_statuses()

        # 统计各状态数量
        completed = 0
        processing = 0
        failed = 0
        pending = 0

        # 遍历所有实际视频，判断其处理状态
        for video in all_videos:
            aweme_id = video.aweme_id
            status_data = all_statuses.get(aweme_id, {})
            status = status_data.get("status", "pending")

            if status == "completed":
                completed += 1
            elif status == "processing":
                processing += 1
            elif status == "failed":
                failed += 1
            else:
                pending += 1

        # 计算总数
        total = len(all_videos)

        # 计算成功率
        success_rate = 0.0
        if completed + failed > 0:
            success_rate = round(completed / (completed + failed), 2)

        return StatsResponse(
            total=total,
            completed=completed,
            processing=processing,
            failed=failed,
            pending=pending,
            success_rate=success_rate
        )

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "processor_ready": processor is not None
    }


@router.post("/api/aweme/{aweme_id}/read", response_model=ActionResponse)
async def mark_aweme_read(aweme_id: str, request: MarkReadRequest):
    """标记已读/未读（重命名自 /api/videos/{aweme_id}/read）"""
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    logger.info(f"标记 aweme 已读状态: {aweme_id}, is_read={request.is_read}")

    try:
        # 直接调 mark_read（mark_read 内部已同步 status 字段）
        await processor.status_manager.mark_read(aweme_id, request.is_read)

        return ActionResponse(
            success=True,
            message=f"已{'标记已读' if request.is_read else '标记未读'}"
        )
    except Exception as e:
        logger.error(f"标记已读失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/aweme/{aweme_id}", response_model=ActionResponse)
async def delete_aweme(aweme_id: str, keep_file: bool = False):
    """用户主动删（重命名自 /api/videos/{aweme_id}）

    行为：
      1. 如果不保留文件，调 file-system-go 删物理文件
      2. status.json 标 deleted（mark_deleted，保留记录）
      3. 不删 status.json 里的记录（与 cleanup 区分）
    """
    if processor is None:
        raise HTTPException(status_code=500, detail="处理器未初始化")

    action = "删除记录" if keep_file else "删除视频"
    logger.info(f"{action}: {aweme_id}")

    try:
        # 1. 调 file-system-go 删物理文件
        if not keep_file:
            file_deleted = await processor.filesystem_client.delete_file(f"{aweme_id}.wav")
            if file_deleted:
                logger.info(f"已删除 file-system-go 上的文件: {aweme_id}")
            else:
                logger.warning(f"file-system-go 文件删除失败或不存在: {aweme_id}")

        # 2. 标 deleted（保留记录）
        await processor.status_manager.mark_deleted(aweme_id)

        # 3. 删 result json
        result_file = Path(processor.output_dir) / f"{aweme_id}.json"
        if result_file.exists():
            result_file.unlink()
            logger.info(f"已删除结果文件: {result_file}")

        # 4. 清缓存
        processor.filesystem_client.invalidate_video_list_cache()

        return ActionResponse(
            success=True,
            message="已删除"
        )
    except Exception as e:
        logger.error(f"{action}失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

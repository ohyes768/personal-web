"""
状态管理器
管理视频处理状态，使用 JSON 文件存储
"""

import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime
from loguru import logger

from src.models import ProcessStatus
from src.utils import load_json, save_json


class StatusManager:
    """状态管理器"""

    def __init__(self, status_file: str = "data/status.json", output_dir: str = "data/output"):
        """初始化状态管理器

        Args:
            status_file: 状态文件路径
            output_dir: 转写结果输出目录（mark_processed 时同步写入，兼容旧 GET /api/videos/{id}/result 端点）
        """
        self.status_file = Path(status_file)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 加载现有状态
        self._lock = asyncio.Lock()
        self._data = self._load()

        logger.info(f"状态管理器初始化完成: {status_file} (output_dir={output_dir})")

    def _load(self) -> dict:
        """加载状态文件"""
        if self.status_file.exists():
            return load_json(str(self.status_file))
        return {
            "last_updated": datetime.now().isoformat(),
            "videos": {}
        }

    def _save(self):
        """保存状态文件"""
        self._data["last_updated"] = datetime.now().isoformat()
        save_json(self._data, str(self.status_file))

    async def get_status(self, aweme_id: str) -> Optional[str]:
        """获取视频处理状态

        Args:
            aweme_id: 视频 ID

        Returns:
            状态（pending/processing/completed/failed），不存在返回 None
        """
        async with self._lock:
            video_data = self._data.get("videos", {}).get(aweme_id)
            return video_data.get("status") if video_data else None

    async def set_status(
        self,
        aweme_id: str,
        status: str,
        error: str = ""
    ):
        """设置视频处理状态

        Args:
            aweme_id: 视频 ID
            status: 状态
            error: 错误信息
        """
        async with self._lock:
            now = datetime.now().isoformat()

            if aweme_id not in self._data.get("videos", {}):
                self._data.setdefault("videos", {})[aweme_id] = {
                    "created_at": now
                }

            self._data["videos"][aweme_id].update({
                "status": status,
                "updated_at": now
            })

            if error:
                self._data["videos"][aweme_id]["error"] = error

            self._save()

    async def mark_processing(self, aweme_id: str):
        """标记为处理中"""
        await self.set_status(aweme_id, "processing")

    async def mark_completed(self, aweme_id: str):
        """标记为已完成"""
        await self.set_status(aweme_id, "completed")

    async def mark_failed(self, aweme_id: str, error: str):
        """标记为失败"""
        await self.set_status(aweme_id, "failed", error)

    async def is_completed(self, aweme_id: str) -> bool:
        """检查视频是否已完成处理"""
        status = await self.get_status(aweme_id)
        return status == "completed"

    async def is_processing(self, aweme_id: str) -> bool:
        """检查视频是否正在处理"""
        status = await self.get_status(aweme_id)
        return status == "processing"

    async def is_failed(self, aweme_id: str) -> bool:
        """检查视频是否处理失败"""
        status = await self.get_status(aweme_id)
        return status == "failed"

    async def get_pending_count(self) -> int:
        """获取待处理视频数量"""
        async with self._lock:
            videos = self._data.get("videos", {})
            return sum(1 for v in videos.values() if v.get("status") == "pending")

    async def get_all_statuses(self) -> dict:
        """获取所有视频状态"""
        async with self._lock:
            return self._data.get("videos", {}).copy()

    async def mark_read(self, aweme_id: str, is_read: bool = True):
        """标记视频已读/未读

        Args:
            aweme_id: 视频 ID
            is_read: 是否已读
        """
        async with self._lock:
            now = datetime.now().isoformat()

            if aweme_id not in self._data.get("videos", {}):
                self._data.setdefault("videos", {})[aweme_id] = {
                    "created_at": now
                }

            if is_read:
                self._data["videos"][aweme_id]["is_read"] = True
                self._data["videos"][aweme_id]["read_at"] = now
                self._data["videos"][aweme_id]["status"] = "read"
            else:
                self._data["videos"][aweme_id]["is_read"] = False
                self._data["videos"][aweme_id]["read_at"] = None
                # 撤回 read 标回 unread
                if self._data["videos"][aweme_id].get("status") == "read":
                    self._data["videos"][aweme_id]["status"] = "unread"

            self._save()
            logger.info(f"视频 {aweme_id} 已标记为 {'已读' if is_read else '未读'}")

    async def hard_delete(self, aweme_id: str):
        """硬删除视频（从状态文件移除）

        Args:
            aweme_id: 视频 ID
        """
        async with self._lock:
            videos = self._data.get("videos", {})
            if aweme_id in videos:
                del videos[aweme_id]
                self._save()
                logger.info(f"视频 {aweme_id} 已从状态文件中删除")

    async def get_read_status(self, aweme_id: str) -> dict:
        """获取视频已读/收藏状态

        Args:
            aweme_id: 视频 ID

        Returns:
            包含 is_read 和 read_at 的字典
        """
        async with self._lock:
            video_data = self._data.get("videos", {}).get(aweme_id, {})
            return {
                "is_read": video_data.get("is_read", False),
                "read_at": video_data.get("read_at")
            }

    # ========== 新增方法（按用户旅程） ==========

    async def mark_pending(
        self,
        aweme_id: str,
        audio_filename: str,
        title: str = "",
        author: str = "",
        description: str = "",
        video_publish_time: str = "",
    ):
        """追加待处理（douyin-collector 调）"""
        async with self._lock:
            now = datetime.now().isoformat()
            record = self._data.setdefault("videos", {}).setdefault(aweme_id, {
                "created_at": now
            })
            record.update({
                "status": "pending",
                "pending_at": now,
                "updated_at": now,
                "audio_filename": audio_filename,
                "title": title,
                "author": author,
                "description": description,
                "video_publish_time": video_publish_time,
            })
            self._save()
            logger.info(f"视频 {aweme_id} 已加入待处理")

    async def mark_processed(self, aweme_id: str, transcript: dict = None):
        """标记处理完（ASR 完成）→ 状态变为 unread

        v2.0: 同时把 transcript 写入 data/output/{aweme_id}.json，
        兼容旧 GET /api/videos/{aweme_id}/result 端点（读 output 文件）
        """
        import json
        async with self._lock:
            now = datetime.now().isoformat()
            record = self._data.setdefault("videos", {}).setdefault(aweme_id, {
                "created_at": now
            })
            record.update({
                "status": "unread",
                "processed_at": now,
                "updated_at": now,
                "is_read": False,
                "read_at": None,
            })
            self._save()
            logger.info(f"视频 {aweme_id} 已处理完，标记为未读")

        # 同步写入 output 文件（兼容旧端点）
        if transcript:
            try:
                output_file = self.output_dir / f"{aweme_id}.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(transcript, f, ensure_ascii=False, indent=2)
                logger.debug(f"已写入转写结果: {output_file}")
            except Exception as e:
                logger.warning(f"写入 output 文件失败: {aweme_id}, {e}")

    async def mark_unread(self, aweme_id: str):
        """标回未读（用户撤回已读时用）"""
        await self.mark_read(aweme_id, is_read=False)

    async def list_pending(self) -> list:
        """返回所有 status=pending 的记录（含 metadata）"""
        async with self._lock:
            videos = self._data.get("videos", {})
            return [
                {
                    "aweme_id": aid,
                    "audio_filename": r.get("audio_filename", f"{aid}.wav"),
                    "title": r.get("title", ""),
                    "author": r.get("author", ""),
                    "description": r.get("description", ""),
                    "pending_at": r.get("pending_at"),
                }
                for aid, r in videos.items()
                if r.get("status") == "pending"
            ]

    async def cleanup_old_records(self, days: int) -> list:
        """清理 status=unread/read 且 processed_at 超过 N 天的记录

        Returns:
            删掉的 aweme_id 列表（供 caller 调 file-system-go 删文件）
        """
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        to_delete = []
        async with self._lock:
            videos = self._data.get("videos", {})
            for aid, r in list(videos.items()):
                status = r.get("status")
                if status in ("unread", "read"):
                    processed_at = r.get("processed_at")
                    if processed_at and processed_at < cutoff:
                        to_delete.append(aid)
            for aid in to_delete:
                del videos[aid]
            if to_delete:
                self._save()
                logger.info(f"已清理 {len(to_delete)} 条过期记录")
        return to_delete

    async def get_status_detail(self, aweme_id: str) -> dict:
        """增强版 status 查询：返回 known/status/audio_filename"""
        async with self._lock:
            videos = self._data.get("videos", {})
            record = videos.get(aweme_id)
            if record is None:
                return {"known": False, "status": None, "audio_filename": None}
            return {
                "known": True,
                "status": record.get("status"),
                "audio_filename": record.get("audio_filename", f"{aweme_id}.wav"),
            }

    async def mark_deleted(self, aweme_id: str):
        """用户主动删（标 deleted_at，保留记录）"""
        async with self._lock:
            now = datetime.now().isoformat()
            record = self._data.setdefault("videos", {}).setdefault(aweme_id, {
                "created_at": now
            })
            record.update({
                "status": "deleted",
                "deleted_at": now,
                "updated_at": now,
            })
            self._save()
            logger.info(f"视频 {aweme_id} 已标记为 deleted")

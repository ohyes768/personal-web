"""
数据模型定义
定义所有使用的数据结构
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class VideoInfo:
    """视频信息"""
    aweme_id: str              # 视频ID
    title: str                 # 视频标题
    author: str                # 作者昵称
    video_url: str             # 视频URL
    desc: str = ""             # 视频描述
    create_time: int = 0       # 创建时间戳
    share_url: str = ""        # 抖音分享链接
    is_product: bool = False   # 是否为商品视频


@dataclass
class TranscriptSegment:
    """转写文本片段"""
    start_time: float          # 开始时间（秒）
    end_time: float            # 结束时间（秒）
    text: str                  # 文本内容
    confidence: float = 0.0    # 置信度（0-1）


@dataclass
class TranscriptResult:
    """转写结果"""
    text: str                  # 完整文本
    segments: list[TranscriptSegment] = field(default_factory=list)  # 分段文本
    confidence: float = 0.0    # 整体置信度
    audio_duration: float = 0.0  # 音频时长（秒）
    has_transcript: bool = True  # 是否有文字内容（False 表示 ASR 跑完但无解说）


@dataclass
class ProcessStatus:
    """处理状态"""
    aweme_id: str
    status: str                # pending/processing/completed/failed
    created_at: str
    updated_at: str
    error: str = ""            # 错误信息


@dataclass
class VideoFile:
    """视频文件信息"""
    aweme_id: str
    filename: str
    size: int
    url: str = ""


@dataclass
class ProcessResult:
    """处理结果"""
    aweme_id: str
    success: bool
    video_info: Optional[VideoInfo] = None
    transcript: Optional[TranscriptResult] = None
    error_message: str = ""
    process_time: float = 0.0


@dataclass
class VideoMetadata:
    """视频元数据（来自 file-system-go）"""
    filename: str               # 文件名（如 7609169800750206794.wav）
    title: str                  # 视频标题
    author: str                 # 作者名称
    description: str = ""       # 视频描述
    upload_time: str = ""       # 视频原发布时间（ISO 8601 格式，来自 file-system-go / douyin-collector）

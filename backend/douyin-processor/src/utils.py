"""
工具函数模块
提供日志、配置、文件操作等工具函数
"""

import os
import json
from pathlib import Path
from typing import Any, Optional
from loguru import logger


def setup_logger(
    name: str = "douyin-processor",
    log_dir: str = "logs",
    level: str = "INFO"
) -> None:
    """配置日志器

    Args:
        name: 日志器名称
        log_dir: 日志目录
        level: 日志级别
    """
    # 移除默认处理器
    logger.remove()

    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 控制台输出
    logger.add(
        sink=lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=level,
        colorize=True,
    )

    # 文件输出
    logger.add(
        sink=log_path / "{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level=level,
        rotation="100 MB",
        retention="7 days",
        encoding="utf-8",
    )


def load_config(config_path: str) -> dict:
    """加载配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典

    Raises:
        FileNotFoundError: 配置文件不存在
        yaml.YAMLError: YAML格式错误
    """
    import yaml

    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config if config else {}


def save_json(
    data: dict,
    filepath: str,
    indent: int = 2,
    ensure_ascii: bool = False
) -> None:
    """保存JSON文件

    Args:
        data: 要保存的数据
        filepath: 文件路径
        indent: 缩进空格数
        ensure_ascii: 是否确保ASCII编码
    """
    file_path = Path(filepath)

    # 创建父目录
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)


def load_json(filepath: str) -> dict:
    """加载JSON文件

    Args:
        filepath: 文件路径

    Returns:
        数据字典

    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: JSON格式错误
    """
    file_path = Path(filepath)

    if not file_path.exists():
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data if data else {}


def format_duration(seconds: float) -> str:
    """格式化时长

    Args:
        seconds: 秒数

    Returns:
        格式化后的时长字符串（如：1:23:45）
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def get_file_size(filepath: str) -> int:
    """获取文件大小

    Args:
        filepath: 文件路径

    Returns:
        文件大小（字节）
    """
    file_path = Path(filepath)

    if not file_path.exists():
        return 0

    return file_path.stat().st_size


def ensure_dir(dir_path: str) -> None:
    """确保目录存在

    Args:
        dir_path: 目录路径
    """
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def delete_file(filepath: str) -> bool:
    """删除文件

    Args:
        filepath: 文件路径

    Returns:
        是否成功删除
    """
    file_path = Path(filepath)

    if not file_path.exists():
        return False

    try:
        file_path.unlink()
        return True
    except Exception:
        return False


def format_size(size_bytes: int) -> str:
    """格式化文件大小

    Args:
        size_bytes: 字节数

    Returns:
        格式化后的大小字符串（如：1.5 MB）
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

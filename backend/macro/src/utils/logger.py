"""日志配置模块"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMATTER = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_SCHEDULER_LOGGER_NAME = "scheduler"


def setup_logger(name: str = "macro", log_dir: str = "logs") -> logging.Logger:
    """配置日志记录器

    Args:
        name: 日志记录器名称
        log_dir: 日志目录

    Returns:
        配置好的日志记录器
    """
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 文件处理器
    file_handler = logging.FileHandler(log_path / "service.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    file_handler.setFormatter(_FORMATTER)
    console_handler.setFormatter(_FORMATTER)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    if name == _SCHEDULER_LOGGER_NAME:
        _attach_scheduler_file(logger, log_path)
        _attach_apscheduler_logger(log_path)

    return logger


def _attach_scheduler_file(logger: logging.Logger, log_path: Path) -> None:
    """独立滚动文件，方便 grep / 拷出 scheduler.log 排查定时任务。"""
    handler = RotatingFileHandler(
        log_path / "scheduler.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(_FORMATTER)
    logger.addHandler(handler)


def _attach_apscheduler_logger(log_path: Path) -> None:
    """APScheduler 内部 misfire / 执行日志：scheduler.log + service.log + 控制台。"""
    aps = logging.getLogger("apscheduler")
    aps.setLevel(logging.INFO)
    if aps.handlers:
        return
    sched_handler = RotatingFileHandler(
        log_path / "scheduler.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    sched_handler.setFormatter(_FORMATTER)
    service_handler = logging.FileHandler(log_path / "service.log", encoding="utf-8")
    service_handler.setFormatter(_FORMATTER)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(_FORMATTER)
    aps.addHandler(sched_handler)
    aps.addHandler(service_handler)
    aps.addHandler(console_handler)

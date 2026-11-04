"""
按源文件签名缓存的只读派生快照。

签名 = (实际路径, mtime_ns, size)。源文件被原子替换、切换季度文件或被删除后，
下一次读取自动重建；"缺失后补齐"（签名从 None 变为元组）同理。不依赖固定 TTL。

约定：
- 构建在锁内串行执行，同签名并发请求只构建一次（构建去重）。
- 构建抛异常时不发布任何缓存，下一次请求重试读取（坏文件不会变成永久空快照）。
- 构建前后各探测一次签名，源在构建期间被替换则换新签名重试（有界）。
- get 返回的是共享只读对象，消费者不得修改。
"""
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# (路径字符串, mtime_ns, size)；源不可用时为 None
Signature = Optional[tuple[str, int, int]]


def file_signature(path: Optional[Path]) -> Signature:
    """返回文件的 (路径, mtime_ns, size) 签名；路径为空或不可 stat 时返回 None。"""
    if path is None:
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path), st.st_mtime_ns, st.st_size)


class VersionedSnapshot:
    """单个源签名对应一份派生结果的缓存器。"""

    def __init__(self, name: str, build: Callable[[], Any], max_attempts: int = 3):
        """
        Args:
            name: 日志用名称
            build: 无参构建函数，返回派生结果；失败应抛异常而不是返回空结果
            max_attempts: 源在构建期间被替换时的最大重试轮数
        """
        self._name = name
        self._build = build
        self._max_attempts = max(1, max_attempts)
        self._lock = threading.Lock()
        self._signature: Signature = None
        self._value: Any = None

    def get(self, probe: Callable[[], Signature]) -> Any:
        """按 probe() 探测的当前签名取值：命中复用，否则锁内重建并复查。"""
        value: Any = None
        for _ in range(self._max_attempts):
            signature = probe()
            with self._lock:
                if signature is not None and signature == self._signature:
                    return self._value
                value = self._build()
                if probe() == signature:
                    self._signature = signature
                    self._value = value
                    return value
        logger.warning(f"{self._name} 源文件在读取期间持续变化，本次结果不缓存")
        return value

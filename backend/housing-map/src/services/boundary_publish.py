"""基础轮廓文件的发布锁。

所有服务内写基础轮廓文件的入口(旧批量导入、后台重建)与读取基础层做版本判定的人工
覆盖操作(应用/撤销)共用这一把锁:重建在锁外计算、锁内原子替换文件;应用/撤销在锁内
重新读取基础状态并比对 revision,避免重建把人工确认结果吞掉或让版本判定读到半个文件。

联网与几何计算不持锁 —— 锁只覆盖"读基础层 → 比对 → 写"的短窗口。
"""
import threading

_publish_lock = threading.RLock()


def publish_lock() -> threading.RLock:
    return _publish_lock

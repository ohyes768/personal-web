"""skill-manager 测试共享探测与标记。

Windows 开发机上创建 symlink 需要 SeCreateSymbolicLinkPrivilege
（开发者模式或管理员终端）；生产发布目标 NAS Linux 不存在此限制。
无特权时依赖真实 symlink 的测试显式 skip（标记 `requires_symlink`），
不伪造文件系统语义。
"""

import os
from pathlib import Path

import pytest

_SKIP_REASON = (
    "当前 Windows 进程无 symlink 创建特权（需开发者模式或管理员终端），"
    "无法创建真实符号链接；NAS Linux 生产环境不受影响。"
    "开启 Windows 开发者模式或在管理员终端重跑即可执行。"
)


def _probe_symlink_privilege() -> bool:
    """用 basetemp 同目录做一次真实 symlink 探测，随后清理。"""
    probe_root = Path(".pytest-tmp")
    probe_root.mkdir(exist_ok=True)
    target = probe_root / "symlink-probe-target"
    target.mkdir(exist_ok=True)
    link = probe_root / "symlink-probe-link"
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except OSError:
        return False
    finally:
        if link.is_symlink():
            link.unlink()
        if target.is_dir():
            target.rmdir()


_HAS_SYMLINK_PRIVILEGE = _probe_symlink_privilege()


def pytest_collection_modifyitems(config, items):
    if _HAS_SYMLINK_PRIVILEGE:
        return
    skip_marker = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        if "requires_symlink" in item.keywords:
            item.add_marker(skip_marker)

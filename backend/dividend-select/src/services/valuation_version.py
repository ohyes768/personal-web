"""Installed valuation skill metadata, separate from model-reported provenance.

与 quality_version.py 同一模式：部署版本从环境变量读取，绝不从本地源码或旧报告推断。
- HERMES_VALUATION_SKILL_VERSION：显式覆盖
- HERMES_VALUATION_SKILL_PATH：已部署 skill 的 SKILL.md 路径（NAS 挂载，只读）
两者都没有 → None（幂等键退化为 unknown-{attempt_id}，跳过版本比对）。
"""
import os
import re
from pathlib import Path

import yaml

VERSION_PATTERN = r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?"


def current_valuation_skill_version() -> str | None:
    """Read deployed metadata fresh; never infer it from local source or old reports."""
    version = os.environ.get("HERMES_VALUATION_SKILL_VERSION", "").strip()
    if not version:
        path = os.environ.get("HERMES_VALUATION_SKILL_PATH", "")
        if not path:
            return None
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
            parts = text.split("---", 2)
            if len(parts) != 3 or parts[0].strip():
                return None
            metadata = yaml.safe_load(parts[1])
            version = (metadata or {}).get("metadata", {}).get("version")
        except (OSError, ValueError, AttributeError, yaml.YAMLError):
            return None
    return version if isinstance(version, str) and re.fullmatch(VERSION_PATTERN, version) else None

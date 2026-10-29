"""Installed skill metadata, separate from model-reported rating provenance."""
import os
import re
from pathlib import Path

import yaml

VERSION_PATTERN = r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?"


def current_quality_skill_version() -> str | None:
    """Read deployed metadata fresh; never infer it from local source or old scores."""
    version = os.environ.get('HERMES_QUALITY_SKILL_VERSION', '').strip()
    if not version:
        path = os.environ.get('HERMES_QUALITY_SKILL_PATH', '')
        if not path:
            return None
        try:
            text = Path(path).read_text(encoding='utf-8-sig')
            parts = text.split('---', 2)
            if len(parts) != 3 or parts[0].strip():
                return None
            metadata = yaml.safe_load(parts[1])
            version = (metadata or {}).get('metadata', {}).get('version')
        except (OSError, ValueError, AttributeError, yaml.YAMLError):
            return None
    return version if isinstance(version, str) and re.fullmatch(VERSION_PATTERN, version) else None

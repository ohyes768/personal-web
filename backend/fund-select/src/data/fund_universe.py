"""
基金宇宙：读 backend/config/funds.yaml（v1 不扫全市场）
"""
from pathlib import Path

import yaml

from src.utils.config import get_funds_config_path
from src.utils.logger import setup_logger

logger = setup_logger("fund-select.universe")


def load_fund_codes(config_path: Path | None = None) -> list[str]:
    """读取配置名单。返回 6 位代码列表；文件缺失或为空返回空列表。"""
    path = config_path or get_funds_config_path()
    if not path.exists():
        logger.error("基金配置文件不存在: %s", path)
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        logger.error("基金配置文件解析失败: %s", e)
        return []

    funds = data.get("funds") if isinstance(data, dict) else None
    if not funds:
        logger.error("基金配置为空: %s", path)
        return []
    codes = [str(c).strip().zfill(6) for c in funds if str(c).strip()]
    logger.info("已加载 %d 只基金配置", len(codes))
    return codes

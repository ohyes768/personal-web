"""
股票信息服务
批量查询股票的行业/概念信息
"""
from typing import Optional

import pandas as pd

from src.api.helpers.aux_data import find_latest_aux_file
from src.utils.logger import setup_logger
from src.utils.helpers import CODE_DTYPE
from src.services.versioned_snapshot import VersionedSnapshot, file_signature

logger = setup_logger(__name__)


class StockInfoService:
    """
    股票信息服务

    功能：
    1. 批量查询股票的申万行业信息
    2. 批量查询股票的概念板块信息
    3. 批量查询股票的行业板块信息
    """

    def __init__(self):
        """初始化股票信息服务"""
        self._sw_snapshot = VersionedSnapshot("申万行业映射", self._read_sw_mapping)

    def _read_sw_mapping(self) -> pd.DataFrame:
        """按签名缓存构建：读最新申万行业映射并归一代码列。失败抛异常，不发布缓存。"""
        sw_mapping_file = find_latest_aux_file("个股申万行业映射")
        if sw_mapping_file is None or not sw_mapping_file.exists():
            raise FileNotFoundError("申万行业映射文件不存在")

        df = pd.read_csv(sw_mapping_file, encoding="utf-8-sig", dtype=CODE_DTYPE)
        # 处理股票代码格式 (001220.SZ -> 001220)
        df["股票代码"] = df["股票代码"].str.replace(r"\.(SZ|SH)$", "", regex=True)
        logger.info(f"申万行业映射加载成功: {len(df)} 条 from {sw_mapping_file.name}")
        return df

    def get_stocks_info(self, codes: list[str]) -> dict[str, dict]:
        """
        批量获取股票的行业/概念信息

        Args:
            codes: 股票代码列表

        Returns:
            {股票代码: {
                "sw_level1": str,
                "sw_level2": str,
                "sw_level3": str,
            }} 字典
        """
        if not codes:
            return {}

        try:
            sw_df = self._sw_snapshot.get(
                lambda: file_signature(find_latest_aux_file("个股申万行业映射"))
            )
        except Exception as e:
            logger.error(f"加载申万行业映射失败: {e}")
            return {}

        # 统一转为 6 位字符串匹配
        codes_formatted = [str(c).zfill(6) for c in codes]

        # 筛选
        filtered_df = sw_df[sw_df["股票代码"].isin(codes_formatted)]

        if filtered_df.empty:
            return {}

        result = {}
        for _, row in filtered_df.iterrows():
            code = str(row["股票代码"])
            result[code] = {
                "sw_level1": str(row.get("一级行业", "")) if pd.notna(row.get("一级行业")) else None,
                "sw_level2": str(row.get("二级行业", "")) if pd.notna(row.get("二级行业")) else None,
                "sw_level3": str(row.get("三级行业", "")) if pd.notna(row.get("三级行业")) else None,
            }

        return result

    def get_stock_info(self, code: str) -> Optional[dict]:
        """
        获取单只股票的行业/概念信息

        Args:
            code: 6位股票代码

        Returns:
            股票信息字典，如果不存在返回 None
        """
        result = self.get_stocks_info([code])
        return result.get(str(code).zfill(6))


# 全局单例
_stock_info_service: StockInfoService | None = None


def get_stock_info_service(data_reader) -> StockInfoService:
    """
    获取股票信息服务单例

    Args:
        data_reader: DataReader 实例（已废弃，仅保留签名兼容）

    Returns:
        StockInfoService 实例
    """
    global _stock_info_service
    if _stock_info_service is None:
        _stock_info_service = StockInfoService()
    return _stock_info_service

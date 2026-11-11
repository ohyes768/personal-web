"""
数据筛选服务
"""
from typing import Optional

import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def normalize_search_keyword(keyword: Optional[str]) -> str:
    """
    搜索关键词归一：去掉首尾空格；空值/空串视为未搜索。

    模块级函数（不是 service 实例方法）：路由的控制流依赖它，
    换成实例方法会被 mock 掉的 service 破坏（实例方法返回 Mock 对象 → 恒真）。
    """
    return (keyword or "").strip()


class FilterService:
    """
    数据筛选服务
    提供按条件筛选数据的功能
    """

    # 股息率列名映射
    YIELD_COLUMNS = {
        "avg_yield_3y": "3年平均股息率(%)",
        "yield_2025": "2025年股息率(%)",
        "yield_2024": "2024年股息率(%)",
        "yield_2023": "2023年股息率(%)",
    }

    def filter_by_yield_range(
        self,
        df: pd.DataFrame,
        min_yield: Optional[float],
        max_yield: Optional[float],
        field: str = "avg_yield_3y"
    ) -> pd.DataFrame:
        """
        按股息率范围筛选

        Args:
            df: 数据 DataFrame
            min_yield: 最小股息率（%）
            max_yield: 最大股息率（%）
            field: 股息率字段（avg_yield_3y, yield_2025, yield_2024, yield_2023）

        Returns:
            筛选后的 DataFrame
        """
        if min_yield is None and max_yield is None:
            return df

        # 获取对应的列名
        col_name = self.YIELD_COLUMNS.get(field)
        if col_name not in df.columns:
            logger.warning(f"股息率列不存在: {col_name}")
            return df

        filtered_df = df.copy()

        # 筛选最小值
        if min_yield is not None:
            # 处理空值和 "-" 标记
            filtered_df[col_name] = pd.to_numeric(
                filtered_df[col_name].replace("-", None),
                errors="coerce"
            )
            filtered_df = filtered_df[
                filtered_df[col_name].fillna(0) >= min_yield
            ]

        # 筛选最大值
        if max_yield is not None:
            filtered_df[col_name] = pd.to_numeric(
                filtered_df[col_name].replace("-", None),
                errors="coerce"
            )
            filtered_df = filtered_df[
                filtered_df[col_name].fillna(999) <= max_yield
            ]

        logger.debug(
            f"股息率筛选: 最小={min_yield}, 最大={max_yield}, "
            f"字段={field}, 结果={len(filtered_df)}条"
        )

        return filtered_df

    def filter_by_exchange(
        self,
        df: pd.DataFrame,
        exchange: Optional[str]
    ) -> pd.DataFrame:
        """
        按交易所筛选

        Args:
            df: 数据 DataFrame
            exchange: 交易所（沪市主板、深市主板）

        Returns:
            筛选后的 DataFrame
        """
        if exchange is None:
            return df

        if "交易所" not in df.columns:
            logger.warning("交易所列不存在")
            return df

        filtered_df = df[df["交易所"] == exchange].copy()

        logger.debug(f"交易所筛选: {exchange}, 结果={len(filtered_df)}条")

        return filtered_df

    def filter_by_industry(
        self,
        df: pd.DataFrame,
        industry: Optional[str]
    ) -> pd.DataFrame:
        """
        按行业筛选（申万一级行业）

        Args:
            df: 数据 DataFrame
            industry: 行业名称

        Returns:
            筛选后的 DataFrame
        """
        if industry is None:
            return df

        if "申万一级行业" not in df.columns:
            logger.warning("申万一级行业列不存在")
            return df

        filtered_df = df[df["申万一级行业"] == industry].copy()

        logger.debug(f"行业筛选: {industry}, 结果={len(filtered_df)}条")

        return filtered_df

    def filter_by_index(
        self,
        df: pd.DataFrame,
        index_name: Optional[str]
    ) -> pd.DataFrame:
        """
        按来源指数筛选

        Args:
            df: 数据 DataFrame
            index_name: 指数名称

        Returns:
            筛选后的 DataFrame
        """
        if index_name is None:
            return df

        if "来源指数" not in df.columns:
            logger.warning("来源指数列不存在")
            return df

        # 支持模糊匹配（因为可能包含多个指数，如"中证红利, 红利增长"）
        filtered_df = df[df["来源指数"].str.contains(index_name, na=False)].copy()

        logger.debug(f"指数筛选: {index_name}, 结果={len(filtered_df)}条")

        return filtered_df

    def filter_by_3y_dividend(
        self,
        df: pd.DataFrame,
        min_avg_yield: float = 3.0
    ) -> pd.DataFrame:
        """
        按3年连续分红筛选

        筛选条件：
        1. 3年平均股息率 >= min_avg_yield
        2. 2023、2024、2025年每年都有分红（每股分红 > 0）

        Args:
            df: 数据 DataFrame
            min_avg_yield: 最小3年平均股息率（%），默认3%

        Returns:
            筛选后的 DataFrame
        """
        filtered_df = df.copy()

        # 转换股息率列为数值
        filtered_df["3年平均股息率(%)"] = pd.to_numeric(
            filtered_df["3年平均股息率(%)"].replace("-", None),
            errors="coerce"
        )
        # 转换各年分红列为数值
        for year in [2023, 2024, 2025]:
            col = f"{year}年分红(元/股)"
            if col in filtered_df.columns:
                filtered_df[col] = pd.to_numeric(
                    filtered_df[col].replace("-", None),
                    errors="coerce"
                )

        # 筛选条件1: 3年平均股息率 >= min_avg_yield
        filtered_df = filtered_df[
            filtered_df["3年平均股息率(%)"].fillna(0) >= min_avg_yield
        ]

        # 筛选条件2: 2023、2024、2025年每年都有分红
        conditions = []
        for year in [2023, 2024, 2025]:
            col = f"{year}年分红(元/股)"
            if col in filtered_df.columns:
                conditions.append(filtered_df[col].fillna(0) > 0)
            else:
                conditions.append(pd.Series([False] * len(filtered_df), index=filtered_df.index))

        # 合并条件：三年每年都有分红
        if len(conditions) == 3:
            has_all_3y = conditions[0] & conditions[1] & conditions[2]
            filtered_df = filtered_df[has_all_3y.values]

        logger.debug(
            f"3年连续分红筛选: 平均股息率>={min_avg_yield}%, "
            f"2023/2024/2025年每年分红>0, 结果={len(filtered_df)}条"
        )

        return filtered_df

    # 搜索相关度分级：数值越小越靠前
    SEARCH_RANK_EXACT_CODE = 0
    SEARCH_RANK_CODE_PREFIX = 1
    SEARCH_RANK_NAME_PREFIX = 2
    SEARCH_RANK_NAME_CONTAINS = 3
    SEARCH_RANK_CODE_CONTAINS = 4
    SEARCH_RANK_OTHER = 5

    @staticmethod
    def normalize_search_keyword(keyword: Optional[str]) -> str:
        """关键词归一：去掉首尾空格；空值/空串视为未搜索。"""
        return normalize_search_keyword(keyword)

    def filter_by_search(self, df: pd.DataFrame, keyword: str) -> pd.DataFrame:
        """
        按股票名称或代码包含匹配过滤。

        语料是**完整收集池**（调用方不得先做股息率/交易所等预筛），
        因此低于阈值、但已被收集的股票同样能被搜到。
        代码按 6 位 str 归一后做子串匹配，前导零不丢。
        """
        key = self.normalize_search_keyword(keyword)
        if not key or df.empty:
            return df

        key_lower = key.lower()
        if "股票名称" in df.columns:
            names = df["股票名称"].astype(str)
            name_hit = names.str.lower().str.contains(key_lower, regex=False, na=False)
        else:
            name_hit = pd.Series(False, index=df.index)
        if "股票代码" in df.columns:
            codes = df["股票代码"].astype(str).str.zfill(6)
            code_hit = codes.str.contains(key, regex=False, na=False)
        else:
            code_hit = pd.Series(False, index=df.index)

        filtered_df = df[name_hit | code_hit]
        logger.debug(f"股票搜索: 关键词='{key}', 结果={len(filtered_df)}条")
        return filtered_df

    def sort_by_search_relevance(self, df: pd.DataFrame, keyword: str) -> pd.DataFrame:
        """
        按搜索相关度排序：代码全等 > 代码前缀 > 名称前缀 > 名称包含 > 代码包含。

        同级按 3 年平均股息率降序，再按代码升序，保证结果稳定。
        """
        key = self.normalize_search_keyword(keyword)
        if not key or df.empty:
            return df

        key_lower = key.lower()
        if "股票代码" in df.columns:
            codes = df["股票代码"].astype(str).str.zfill(6)
        else:
            codes = pd.Series("", index=df.index, dtype="object")
        if "股票名称" in df.columns:
            name_lower = df["股票名称"].astype(str).str.lower()
        else:
            name_lower = pd.Series("", index=df.index, dtype="object")

        rank = pd.Series(self.SEARCH_RANK_OTHER, index=df.index, dtype="int64")
        rank = rank.mask(codes.str.contains(key, regex=False, na=False), self.SEARCH_RANK_CODE_CONTAINS)
        rank = rank.mask(name_lower.str.contains(key_lower, regex=False, na=False), self.SEARCH_RANK_NAME_CONTAINS)
        rank = rank.mask(name_lower.str.startswith(key_lower, na=False), self.SEARCH_RANK_NAME_PREFIX)
        rank = rank.mask(codes.str.startswith(key, na=False), self.SEARCH_RANK_CODE_PREFIX)
        rank = rank.mask(codes == key, self.SEARCH_RANK_EXACT_CODE)

        if "3年平均股息率(%)" in df.columns:
            yields = pd.to_numeric(
                df["3年平均股息率(%)"].replace("-", None), errors="coerce"
            ).fillna(-1.0)
        else:
            yields = pd.Series(-1.0, index=df.index)

        sort_columns = ["_search_rank", "_search_yield"]
        ascending = [True, False]
        if "股票代码" in df.columns:
            sort_columns.append("股票代码")
            ascending.append(True)

        ranked = df.assign(_search_rank=rank, _search_yield=yields)
        ranked = ranked.sort_values(
            by=sort_columns, ascending=ascending, kind="stable"
        )
        return ranked.drop(columns=["_search_rank", "_search_yield"])
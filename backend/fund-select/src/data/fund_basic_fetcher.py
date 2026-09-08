"""
基金基础信息 fetcher

雪球源：ak.fund_individual_basic_info_xq(symbol)
返回 item → value 字典。

容错：akshare 内部对列子集做严格选择，遇到「互认基金」类残缺 schema 会抛 KeyError。
这种情况直接走 danjuanfunds 接口 + 自取字段，避免整个 refresh task 失败。
"""
import re
from threading import local as _thread_local

import akshare as ak
import pandas as pd
import requests

from src.utils.logger import setup_logger

logger = setup_logger("fund-select.basic_fetcher")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36"
)

# 复用 Session：thread-local 保 multi-threaded 安全；单线程下零开销
_session_pool = _thread_local()


def _http() -> requests.Session:
    """thread-local Session 单例，复用 TCP 连接 + 默认 UA。"""
    s = getattr(_session_pool, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        _session_pool.session = s
    return s

# akshare 列子集缺失时，fallback 走 danjuanfunds 接口，自行 mapping 字段
_FALLBACK_FIELDS = {
    "fd_code": "基金代码",
    "fd_name": "基金名称",
    "fd_full_name": "基金全称",
    "found_date": "成立时间",
    "keeper_name": "基金公司",
    "manager_name": "基金经理",
    "type_desc": "基金类型",
    "rating_desc": "基金评级",
}


def _clean(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def parse_size(text) -> float | None:
    """'94.51亿' / '12.34万' -> 亿元；无法解析返回 None"""
    t = _clean(text)
    if not t or t == "暂无数据":
        return None
    m = re.match(r"([\d.]+)\s*(亿|万)", t)
    if not m:
        return None
    v = float(m.group(1))
    return v if m.group(2) == "亿" else v / 1e4


def fetch_basic(code: str) -> dict:
    """拉基础信息，返回 item -> value 字典。失败抛异常（让 L2 流水线跳过单只失败）。

    雪球对个别基金（如 968157 互认基金）schema 残缺，akshare 列子集 KeyError。
    注意：之前 fallback 走 danjuanfunds 接口，但该接口 schema 已变化（'data' key 丢失），
    两步失败无意义。直接抛异常让上层处理。
    """
    df = ak.fund_individual_basic_info_xq(symbol=code)
    return {row["item"]: row["value"] for _, row in df.iterrows()}


def _fetch_basic_fallback(code: str) -> dict:
    """【已弃用】保留仅为兼容；现在直接抛异常由 L2 pipeline 跳过单只失败。

    之前走 danjuanfunds.com/djapi/fund/{code} 接口，但该接口 schema 已变（'data' key 丢失），
    fallback 实际是死路。
    """
    raise NotImplementedError(
        f"fallback danjuanfunds for {code} is no longer reliable; "
        "fetch_basic now propagates exceptions to the L2 pipeline."
    )
    for k_eng, k_ch in _FALLBACK_FIELDS.items():
        v = data.get(k_eng)
        if v is None:
            continue
        if k_eng == "type_desc":
            # 互认基金（如 968157 东亚联丰环球股票）标准化为 QDII-互认，便于展示
            out[k_ch] = "QDII-互认" if str(v).strip() == "互认基金" else str(v).strip()
        else:
            out[k_ch] = str(v).strip()
    return out

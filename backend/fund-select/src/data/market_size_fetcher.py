"""
size_yi + age_years 单只 fetcher（东财移动端 msm 接口）

URL: https://fundmobapi.eastmoney.com/FundMNewApi/FundMNBasicInformation?FCODE={code}
字段映射：
  ESTABDATE → established_date (date)
  ENDNAV    → size_yi（ENDNAV 单位为元，÷1e8 = 亿元）
  JJGS      → mgr_company（覆盖 L0 阶段的第一只经理公司，可能更准）

单只 ~0.4s + 0.4s sleep；只在 L1 预筛后 ~1573 只上跑。
"""
import time
from datetime import date as _date

import requests

from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_size")

USER_AGENT = (
    # iOS Safari UA：实测 Chrome UA 触发「网络繁忙，请稍后重试」限频；
    # fundmobapi 是移动端接口，移动端 UA 不限频。
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
REFERER = "https://fund.eastmoney.com/"
DELAY_S = 0.4  # 防东财移动端限频
URL = (
    "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNBasicInformation"
    "?FCODE={code}&deviceid=W&plat=Wap&product=EFund&version=2.0.0"
)


def fetch_size(code: str, delay_s: float = DELAY_S) -> dict | None:
    """单只基金 size_yi / age_years / established_date / mgr_company。失败返回 None。"""
    time.sleep(delay_s)
    try:
        r = requests.get(
            URL.format(code=code),
            timeout=15,
            headers={"User-Agent": USER_AGENT, "Referer": REFERER},
        )
        r.raise_for_status()
        d = r.json().get("Datas") or {}
        if not d:
            return None

        ed_str = d.get("ESTABDATE")
        established_date: _date | None = None
        age_years: float | None = None
        if ed_str and len(ed_str) >= 10:
            established_date = _date.fromisoformat(ed_str[:10])
            age_years = round((_date.today() - established_date).days / 365.25, 2)

        endnav = d.get("ENDNAV")
        size_yi: float | None = None
        if endnav is not None:
            try:
                size_yi = round(float(endnav) / 1e8, 4)  # 元 → 亿元
            except (TypeError, ValueError):
                size_yi = None

        mgr_company_raw = d.get("JJGS")
        mgr_company: str | None = None
        if mgr_company_raw is not None:
            s = str(mgr_company_raw).strip()
            mgr_company = s or None

        return {
            "code": code,
            "established_date": established_date,
            "age_years": age_years,
            "size_yi": size_yi,
            "mgr_company": mgr_company,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("FundMNBasicInformation %s 失败: %s", code, str(e)[:120])
        return None


def fetch_market_size(codes: list[str], delay_s: float = DELAY_S) -> list[dict]:
    """逐只拉 size_yi + age_years + established_date + mgr_company。

    Returns:
        [{code, established_date, age_years, size_yi, mgr_company}, ...]
    """
    rows: list[dict] = []
    total = len(codes)
    if total:
        logger.info("fetch_market_size 开始: %d 只", total)
    for i, code in enumerate(codes, 1):
        data = fetch_size(code, delay_s=delay_s)
        if data is not None:
            rows.append(data)
        # 每 200 只（或最后一只）打一行进度
        if i % 200 == 0 or i == total:
            logger.info("fetch_market_size 进度: %d/%d (%.0f%%) 成功 %d",
                        i, total, 100 * i / total, len(rows))
    return rows

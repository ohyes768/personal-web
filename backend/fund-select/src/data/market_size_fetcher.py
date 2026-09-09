"""
size_yi + age_years 单只 fetcher（雪球优先 + 东财 fallback）

主路径：雪球 ak.fund_individual_basic_info_xq（5 worker 并发 ~0.64s/只，93% 成功率）
fallback：东财移动端 msm（单线程 0.4s/只，连续大批量请求限流严重）

雪球字段映射：
  最新规模  → size_yi（"X.XX亿" / "X.XX万"）
  成立时间  → established_date（YYYY-MM-DD）
  基金管理人 → mgr_company（兜底字段）

东财字段映射：
  ESTABDATE → established_date (date)
  ENDNAV    → size_yi（ENDNAV 单位为元，÷1e8 = 亿元）
  JJGS      → mgr_company（覆盖 L0 阶段的第一只经理公司，可能更准）

并发模型：
  - fetch_market_size 用 ThreadPoolExecutor 并发跑雪球（5 worker）
  - 单只内部仍 sleep delay_s（雪球 0.3s / 东财 0.4s）
  - 失败的 code 自动 fallback 东财（仍走东财单线程，限流安全）
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as _date

import akshare as ak
import requests

from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_size")

# ── 并发配置 ─────────────────────────────────────────
MAX_WORKERS = 5  # 雪球并发 worker（实测 5 不触发限频）

# ── 东财移动端 msm 接口（fallback） ─────────────────────────────
USER_AGENT = (
    # iOS Safari UA：实测 Chrome UA 触发「网络繁忙，请稍后重试」限频；
    # fundmobapi 是移动端接口，移动端 UA 不限频。
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
REFERER = "https://fund.eastmoney.com/"
DELAY_S_EASTMONEY = 0.4  # 防东财移动端限频
URL_EASTMONEY = (
    "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNBasicInformation"
    "?FCODE={code}&deviceid=W&plat=Wap&product=EFund&version=2.0.0"
)

# ── 雪球接口（主路径） ──────────────────────────────────────
DELAY_S_XQ = 0.3  # 雪球单只内部 sleep（叠上并发 = 5 QPS，实测不限频）


def fetch_size_xq(code: str, delay_s: float = DELAY_S_XQ) -> dict | None:
    """雪球单只 fetcher（ak.fund_individual_basic_info_xq）。

    Returns: {code, established_date, age_years, size_yi, mgr_company} or None
    """
    time.sleep(delay_s)
    try:
        df = ak.fund_individual_basic_info_xq(symbol=code)
        if df is None or df.empty:
            return None
        # item/value 两列 DataFrame → dict
        d = dict(zip(df["item"].astype(str), df["value"].astype(str)))
        size_yi = _parse_size_yi(d.get("最新规模"))
        established_date = _parse_estab_date(d.get("成立时间"))
        mgr_company = _parse_mgr_company(d.get("基金管理人"))

        # 三个字段全空 → 视为失败
        if size_yi is None and established_date is None and mgr_company is None:
            return None

        age_years = (
            round((_date.today() - established_date).days / 365.25, 2)
            if established_date else None
        )
        return {
            "code": code,
            "established_date": established_date,
            "age_years": age_years,
            "size_yi": size_yi,
            "mgr_company": mgr_company,
        }
    except KeyError as e:
        # 雪球接口 schema 残缺（'data' key 丢失）→ 标记 fallback
        logger.warning("fetch_size_xq %s 失败: %s (will fallback eastmoney)", code, str(e)[:80])
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_size_xq %s 失败: %s (will fallback eastmoney)", code, str(e)[:120])
        return None


def fetch_size_eastmoney(code: str, delay_s: float = DELAY_S_EASTMONEY) -> dict | None:
    """东财移动端 msm 单只 fetcher（fallback 路径）。

    Returns: {code, established_date, age_years, size_yi, mgr_company} or None
    """
    time.sleep(delay_s)
    try:
        r = requests.get(
            URL_EASTMONEY.format(code=code),
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


def fetch_size(
    code: str,
    delay_s_xq: float = DELAY_S_XQ,
    delay_s_eastmoney: float = DELAY_S_EASTMONEY,
) -> dict | None:
    """主入口：雪球优先，雪球失败 fallback 东财。两都失败返回 None。"""
    data = fetch_size_xq(code, delay_s=delay_s_xq)
    if data is not None:
        return data
    return fetch_size_eastmoney(code, delay_s=delay_s_eastmoney)


def fetch_market_size(
    codes: list[str],
    delay_s_xq: float = DELAY_S_XQ,
    delay_s_eastmoney: float = DELAY_S_EASTMONEY,
    max_workers: int = MAX_WORKERS,
) -> list[dict]:
    """并发拉 size_yi + age_years + established_date + mgr_company（雪球优先 + 东财 fallback）。

    雪球走 max_workers 线程池（实测 5 worker 不触发限频）；
    单只内部仍走雪球 → fallback 东财。

    Returns:
        [{code, established_date, age_years, size_yi, mgr_company}, ...]
    """
    rows: list[dict] = []
    total = len(codes)
    if total == 0:
        return rows
    logger.info("fetch_market_size 开始: %d 只 (workers=%d)", total, max_workers)

    def _safe(code: str) -> dict | None:
        try:
            return fetch_size(code, delay_s_xq=delay_s_xq, delay_s_eastmoney=delay_s_eastmoney)
        except Exception as e:  # noqa: BLE001
            logger.warning("fetch_market_size %s 异常: %s", code, str(e)[:120])
            return None

    done = 0
    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {executor.submit(_safe, code): code for code in codes}
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            data = future.result()
            if data is not None:
                out[code] = data
            done += 1
            # 每 200 只（或最后一只）打一行进度
            if done % 200 == 0 or done == total:
                logger.info("fetch_market_size 进度: %d/%d (%.0f%%) 成功 %d",
                            done, total, 100 * done / total, len(out))

    # 按输入顺序返回（as_completed 不保证顺序，但 pipeline 调用方期望稳定顺序）
    rows = [out[c] for c in codes if c in out]
    logger.info("fetch_market_size: %d/%d 只成功", len(rows), total)
    return rows


# ── 雪球字段解析辅助 ──────────────────────────────────────


def _parse_size_yi(size_str) -> float | None:
    """雪球"最新规模"解析：'39.38亿' / '2250.45万' / '1234.56'"""
    if not size_str:
        return None
    s = str(size_str).strip()
    try:
        if s.endswith("亿"):
            return round(float(s[:-1]), 4)
        if s.endswith("万"):
            return round(float(s[:-1]) / 10000, 4)
        return round(float(s), 4)
    except (ValueError, TypeError):
        return None


def _parse_estab_date(estab_str) -> _date | None:
    """雪球"成立时间"解析：'2001-12-18' / '2001-12-18T00:00:00'"""
    if not estab_str or len(estab_str) < 10:
        return None
    try:
        return _date.fromisoformat(estab_str[:10])
    except ValueError:
        return None


def _parse_mgr_company(mgr_str) -> str | None:
    """雪球"基金管理人"解析：'华夏基金管理有限公司' / 空字符串 → None"""
    if not mgr_str:
        return None
    s = str(mgr_str).strip()
    return s or None

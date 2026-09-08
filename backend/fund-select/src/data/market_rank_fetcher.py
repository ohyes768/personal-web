"""
东方财富 rankhandler 批量业绩 fetcher

URL: http://fund.eastmoney.com/data/rankhandler.aspx
参数: op=ph, dt=kf, ft={gp|hh|zq|zs|qdii|lof|fof|bb},
      sc={zzf|1yzf|3nzf|6yzf|...}, st=desc|asc, sd=YYYY-MM-DD, ed=YYYY-MM-DD,
      pi=页码, pn=每页条数(≤50), dx=1
响应: JSONP var rankData = {datas: ["code,name,...,ret_*,..."], allRecords, allPages}
"""
import json
import re
import time
from datetime import date, timedelta

import pandas as pd
import requests

from src.utils.logger import setup_logger

logger = setup_logger("fund-select.market_rank")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
REFERER = "https://fund.eastmoney.com/data/fundranking.html"
RANKHANDLER_URL = "http://fund.eastmoney.com/data/rankhandler.aspx"
PAGE_DELAY_S = 0.5  # 防东财限流

# datas 字段位置（实测）
_FIELDS = [
    "code", "name", "pinyin", "nav_date", "nav_latest", "acc_nav",
    "ret_1d", "ret_1w", "ret_1m", "ret_3m", "ret_6m",
    "ret_1y", "ret_2y", "ret_3y", "ret_ytd", "ret_all",
    "established_date", "ft_code", "size_yi", "fee_buy",
]


def fetch_market_rank_page(ft: str, sd: str, ed: str, pi: int = 1, pn: int = 50,
                            sc: str = "3nzf", st: str = "desc") -> list[dict]:
    """单页 rankhandler 调用。返回 [{code, name, ret_*, ...}]。"""
    params = {
        "op": "ph", "dt": "kf", "ft": ft,
        "sc": sc, "st": st, "sd": sd, "ed": ed,
        "pi": pi, "pn": pn, "dx": 1,
    }
    headers = {"User-Agent": USER_AGENT, "Referer": REFERER}
    r = requests.get(RANKHANDLER_URL, params=params, headers=headers, timeout=15)
    r.raise_for_status()

    m = re.search(r"var\s+rankData\s*=\s*(\{.*?\});", r.text, re.DOTALL)
    if not m:
        raise ValueError(f"rankhandler 响应格式异常（ft={ft} pi={pi}）")
    body = re.sub(r"([{,]\s*)(\w+)(\s*:)", r'\1"\2"\3', m.group(1))
    data = json.loads(body)

    rows: list[dict] = []
    for d in data.get("datas", []):
        parts = d.split(",")
        if len(parts) < len(_FIELDS):
            continue
        row = {f: parts[i] for i, f in enumerate(_FIELDS)}
        row["nav_latest"] = _to_float(row["nav_latest"])
        for k in ("ret_1d", "ret_1w", "ret_1m", "ret_3m", "ret_6m",
                  "ret_1y", "ret_2y", "ret_3y", "ret_ytd", "ret_all"):
            row[k] = _to_float(row[k])
        row["size_yi"] = _to_float(row["size_yi"])
        row["nav_date"] = _to_date(row["nav_date"])
        rows.append(row)
    return rows


def _to_float(v: str) -> float | None:
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _to_date(v: str) -> date | None:
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def fetch_market_rank_bulk(fts: list[str], pages_per_ft: int = 20,
                            sd: str | None = None, ed: str | None = None,
                            page_delay_s: float = PAGE_DELAY_S) -> pd.DataFrame:
    """按 ft 列表分页拉业绩。返回 DataFrame[code, name, nav_date, nav_latest, ret_*, ft_code]."""
    if sd is None:
        ed = ed or date.today().isoformat()
        sd = (date.today() - timedelta(days=365 * 3)).isoformat()

    all_rows: list[dict] = []
    for ft in fts:
        for pi in range(1, pages_per_ft + 1):
            try:
                rows = fetch_market_rank_page(ft=ft, sd=sd, ed=ed, pi=pi, pn=50)
                if not rows:
                    break
                all_rows.extend(rows)
                time.sleep(page_delay_s)
            except Exception as e:
                logger.warning("rankhandler 拉取失败 ft=%s pi=%d: %s", ft, pi, str(e)[:120])
                break

    if not all_rows:
        return pd.DataFrame(columns=["code", "name", "nav_date", "nav_latest",
                                      "ret_1w", "ret_1m", "ret_3m", "ret_6m",
                                      "ret_1y", "ret_2y", "ret_3y", "ret_ytd", "ret_all",
                                      "ft_code"])
    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates("code", keep="first").reset_index(drop=True)
    logger.info("fetch_market_rank_bulk: %d 只 (fts=%s)", len(df), fts)
    return df

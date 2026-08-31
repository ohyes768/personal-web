"""阿里云 alirmcom2 comkm 日 K 翻页（商品 / 股指共用）。

接口：GET /query/comkm?period=D&pidx=N&psize=500&symbol=...&withlast=0
返回倒序（最新在前）。增量传入 since=CSV last_date+1 后，第 1 页通常已覆盖，
不必翻到 10 年上限（Code=-100）。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

import httpx
import pandas as pd

API_PATH = "/query/comkm"
PAGE_SIZE = 500
MAX_PAGES = 20  # 兜底防无限循环；阿里云日 K 实际约 15 页触顶
TEN_YEAR_CAP_CODE = -100


def parse_kline_rows(obj: Any) -> list[dict]:
    """把 comkm Obj 列表解析成 [{date, close}, ...]，坏行跳过。"""
    rows: list[dict] = []
    if not obj:
        return rows
    for item in obj:
        if not isinstance(item, dict):
            continue
        d_str = item.get("D")
        c_val = item.get("C")
        if not d_str or c_val in (None, ""):
            continue
        try:
            rows.append({"date": pd.Timestamp(str(d_str)[:10]), "close": float(c_val)})
        except (ValueError, TypeError):
            continue
    return rows


async def fetch_comkm_klines(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    symbol: str,
    logger,
    since: Optional[date] = None,
) -> list[dict]:
    """翻页拉取单个 symbol 日 K，返回按日期升序的记录。

    since: 只要当前页最旧一根 <= since，即可停止（更新页更旧，增量不需要）。
    Code=-100（最多 10 年内）视为正常翻页结束，保留已拉到的数据。
    HTTP / JSON / 其它非 0 Code：返回已拉到的部分，不抛异常。
    """
    all_records: list[dict] = []
    pidx = 1
    since_ts = pd.Timestamp(since) if since is not None else None
    base = base_url.rstrip("/")

    while pidx <= MAX_PAGES:
        params = (
            f"period=D&pidx={pidx}&psize={PAGE_SIZE}"
            f"&symbol={symbol}&withlast=0"
        )
        url = f"{base}{API_PATH}?{params}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"aliyun comkm {symbol} pidx={pidx} HTTP 失败: {e}")
            break

        try:
            payload = resp.json()
        except Exception as e:
            logger.error(f"aliyun comkm {symbol} pidx={pidx} JSON 解析失败: {e}")
            break

        if not isinstance(payload, dict):
            logger.error(
                f"aliyun comkm {symbol} pidx={pidx} 返回非 dict: {type(payload).__name__}"
            )
            break

        code_val = payload.get("Code")
        if code_val == TEN_YEAR_CAP_CODE:
            logger.info(
                f"aliyun comkm {symbol} pidx={pidx} 到达 10 年上限 (Code=-100)，停止翻页"
            )
            break
        if code_val != 0:
            logger.error(
                f"aliyun comkm {symbol} pidx={pidx} 返回错误: "
                f"Code={code_val}, Msg={payload.get('Msg', '')}"
            )
            break

        page_rows = parse_kline_rows(payload.get("Obj"))
        kline_count = len(payload.get("Obj") or [])
        all_records.extend(page_rows)
        logger.info(
            f"aliyun comkm {symbol} pidx={pidx} 返回 {kline_count} 条，累计 {len(all_records)} 条"
        )

        if kline_count < PAGE_SIZE:
            break

        if since_ts is not None and page_rows:
            oldest = min(r["date"] for r in page_rows)
            if oldest <= since_ts:
                logger.info(
                    f"aliyun comkm {symbol} pidx={pidx} 已覆盖 since={since}，停止翻页"
                )
                break

        pidx += 1

    if pidx > MAX_PAGES:
        logger.warning(f"aliyun comkm {symbol} 翻页超过 {MAX_PAGES} 次，主动停止")

    all_records.sort(key=lambda r: r["date"])
    return all_records

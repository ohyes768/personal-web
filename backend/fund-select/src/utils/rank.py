"""同类排名解析（'1694/5606' → 分位/名次/总数）。

从 filter_service 提取为共享工具：经理明细的历任基金行也要显示
同类排名（与股票 tab 主表同口径），两处共用一份解析，避免漂移。
"""


def parse_peer_rank(value: str | None) -> dict | None:
    """'1694/5606' → {'pct': 30.2, 'total': 5606, 'rank': 1694}；格式异常/缺分母 → None。

    用于股票 tab 同类排名显示；债基 tab 永远返回 None（无入库数据）。
    """
    if not value or "/" not in value:
        return None
    try:
        rank_s, total_s = value.split("/", 1)
        rank = int(rank_s.strip())
        total = int(total_s.strip())
    except (ValueError, TypeError):
        return None
    if rank <= 0 or total <= 0 or rank > total:
        return None
    return {"pct": round(rank / total * 100, 1), "total": total, "rank": rank}

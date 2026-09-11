# Design: 债基全量刷新 L6 阶段补写 fees/holdings

## 架构概览

```
[路由] discovery_bond_full_refresh (routes.py:444)
    │
    │ background.add_task(refresh_market_full_sync,
    │                      universe_filter=DISCOVERY_BOND_SUBTYPES,
    │                      pipeline_profile="bond",   ← 新增参数
    │                      min_ret_3y/min_size_yi/min_mgr_exp)
    │
[Pipeline] refresh_market_full_sync (market_full_pipeline.py)
    │
    │ L0 universe (ak.fund_name_em 全市场)
    │ L1 rank (ak.fund_open_fund_rank_em 5 symbol 全市场)
    │ L2 size (雪球优先 + 东财 msm fallback, codes_after_l1)
    │ L3 nav (ak.fund_open_fund_info_em 并发 5 worker, codes_after_l2)
    │
    │ ★ 新增 L6_fees_holdings（仅 profile=="bond"）
    │   ├─ 二次过滤 codes_after_l2 → market_subtype in DISCOVERY_BOND_SUBTYPES
    │   ├─ ThreadPoolExecutor(max_workers=5) → 单只并发
    │   ├─ 复用 fetch_fees(code) + fetch_bond_hold(code, year) + analyze_holdings
    │   ├─ 复用 persist_snapshot 的写入路径（仅 fees/holdings 字段）
    │   └─ 单只 try/except，errors 累加
    │
    └─ 返回 {stage_results, total, completed, failed}
```

## 关键决策：D1 复用什么、不复用什么

**复用**：
- `src/data/fee_fetcher.py:44 fetch_fees(code, use_cache=True)` → 单只费率 dict
- `src/data/holdings_fetcher.py:20 fetch_bond_hold(code, year, use_cache=True)` → 季报表格 list
- `src/data/holdings_fetcher.py:analyze_holdings(tables)` → 持仓占比聚合
- `src/services/refresh_service.py:116 persist_snapshot(db, snap)` → ORM 写入 `FundFees` / `FundHoldingsBond`

**不复用**：
- `src/services/refresh_service.py:39 snapshot_fund` — 因为它会拉 basic/nav/performance
  （**新套 L0-L3 已写过** `funds` 表 / `market_nav` 表），重复拉浪费 IO
- `compute_performance(nav)` — 同理

**取舍**：不直接 import `snapshot_fund`，而是 L6 阶段只拼 `out["fees"]` 和 `out["holdings"]` 字段，
直接 `persist_snapshot`。`persist_snapshot` 内部用 `snap.get("fees")` / `snap.get("holdings")`
判断写入（line 137 / line 145），缺失则跳过——所以只填两个字段是安全的。

## 接口契约

### `refresh_market_full_sync` 新增参数

```python
def refresh_market_full_sync(
    universe_filter: Optional[list[str]] = None,
    min_ret_3y: Optional[float] = None,
    min_size_yi: Optional[float] = None,
    min_mgr_exp: Optional[float] = None,
    preset_task_id: Optional[str] = None,
    pipeline_profile: str = "stock",       # 新增
) -> dict:
    if pipeline_profile not in ("stock", "bond"):
        raise ValueError(f"pipeline_profile 必须为 'stock' 或 'bond'，当前={pipeline_profile!r}")
```

### `pipeline_profile` 取值规则

| 取值 | 阶段序列 | main_run.total 公式 |
|---|---|---|
| `"stock"`（默认） | L0/L1/L2/L3/L4/L5 | codes × 6 |
| `"bond"` | L0/L1/L2/L3/L6 | codes × 5 |

- 默认 `"stock"` 保持现有股基路由 `discovery_stock_full_refresh` 不传参的兼容性
- 债基路由 `discovery_bond_full_refresh` 显式传 `"bond"`
- 非法值 ValueError 拒收，路由层不依赖隐式默认

### main_run.total 算法（替换 line 192 / line 273）

```python
ACTIVE_STAGES = {
    "stock": ("L0_universe", "L1_rank", "L2_size", "L3_nav", "L4_risk", "L5_achievement"),
    "bond":  ("L0_universe", "L1_rank", "L2_size", "L3_nav", "L6_fees_holdings"),
}
# 在 _run_stage 调用前
n_stages = len(ACTIVE_STAGES[pipeline_profile])
main_run.total = len(codes) * n_stages if codes else n_stages
```

## L6 阶段实现细节

```python
def _stage_l6(d):
    """仅 profile="bond" 触发。复用 fetch_fees + fetch_bond_hold + persist_snapshot。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from src.data.fee_fetcher import fetch_fees
    from src.data.holdings_fetcher import analyze_holdings, fetch_bond_hold
    from src.services.refresh_service import persist_snapshot
    from src.data.market_subtype_map import DISCOVERY_BOND_SUBTYPES

    # 防御性二次过滤：理论上 codes_after_l2 已是债基 universe，但兜底
    bond_codes = list(d.query(Fund.code).filter(
        Fund.code.in_(codes),
        Fund.market_subtype.in_(DISCOVERY_BOND_SUBTYPES),
    ).scalars())

    if not bond_codes:
        return {"task_id": f"{task_id}_L6", "total": 0, "completed": 0, "failed": 0, "errors": []}

    holdings_year = str(date.today().year - 1)  # 默认上年年报（对齐 snapshot_fund:47）
    completed = failed = 0
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            ex.submit(_fetch_one_fees_holdings, code, holdings_year): code
            for code in bond_codes
        }
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                snap = fut.result()
                if snap.get("fees") or snap.get("holdings"):
                    persist_snapshot(d, snap)
                    d.commit()  # 每只立即提交（断点续传，对齐老路径行为）
                completed += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append(f"fees_holdings:{code}: {str(e)[:120]}")
                logger.warning("L6 %s 失败: %s", code, str(e)[:120])

    logger.info("market_full L6: total=%d completed=%d failed=%d", len(bond_codes), completed, failed)
    return {"task_id": f"{task_id}_L6", "total": len(bond_codes), "completed": completed, "failed": failed, "errors": errors}


def _fetch_one_fees_holdings(code: str, year: str) -> dict:
    """单只 fees + holdings 抓取，结果装入 persist_snapshot 期望的 dict 形态。"""
    out: dict = {"code": code, "achievement": None}  # achievement=None 让 persist_snapshot 跳过
    try:
        out["fees"] = fetch_fees(code) or {}
    except Exception:
        out["fees"] = {}
    try:
        tables = fetch_bond_hold(code, year)
        if tables:
            out["holdings"] = {"report_date": date(int(year), 12, 31), **analyze_holdings(tables)}
    except Exception:
        out["holdings"] = None
    return out
```

## 数据流详解

```
codes_after_l2 (债基 universe，已应用所有预筛)
  │
  │ ThreadPoolExecutor(max_workers=5)
  │
  ├→ _fetch_one_fees_holdings(code, year)
  │     │
  │     ├─ fetch_fees(code) → dict 或 {}
  │     │   （失败 → {}，不抛）
  │     │
  │     └─ fetch_bond_hold(code, year) → [DataFrame, ...] 或 []
  │         │
  │         └─ analyze_holdings(tables) → dict (持仓聚合)
  │
  ├→ persist_snapshot(db, snap)
  │     │
  │     ├─ snap.get("fees") truthy → db.merge(FundFees(...))
  │     └─ snap.get("holdings") truthy → db.merge(FundHoldingsBond(...))
  │
  └─ db.commit()  # 每只立即提交
```

## 兼容性 / 边界

| 边界 | 处理 |
|---|---|
| 老路径 `refresh_configured_funds_sync` 不动 | 不调 `refresh_market_full_sync`，独立运行 |
| scheduler/tasks.py:29 `_import_full_pipeline` | 不传 profile，默认 `"stock"`，行为不变 |
| `discovery_bond_refresh`（单层 refresh，非 full） | 不传 profile，不受影响 |
| `discovery_stock_full_refresh` 路由 | 不传 profile，默认 `"stock"`，6 阶段不变 |
| 季报接口返空 | `fetch_bond_hold` 返回 `[]` → `out["holdings"] = None` → `persist_snapshot` 跳过 |
| 单只 fees 抓取失败 | `out["fees"] = {}` → `persist_snapshot` 跳过 → 该只标记 completed（行为选择 D4） |
| 单只 holdings 抓取失败 | 同上 |
| DB 写入失败 | try/except 在 persist_snapshot 外再包一层，errors 累加 |
| 缓存命中 | `use_cache=True` 默认，重复刷新走本地 JSON 不打东财 |

## 回滚

1. 把债基路由 `pipeline_profile="bond"` 删掉 → 回到精简版（4 阶段，无 fees/holdings）
2. 把 `_stage_l6_fees_holdings` 调用删除 → 回到精简版
3. 不动 schema，不动 `fund_fees` / `fund_holdings_bond` 表结构 → 历史数据保留
4. 关键开关：`pipeline_profile` 字符串路由——单一变量控制行为，回滚面最小

## 监控 / 日志

```
logger.info("market_full L6: total=%d completed=%d failed=%d", total, completed, failed)
logger.warning("L6 %s 失败: %s", code, str(e)[:120])
```

复用现有 `setup_logger("fund-select.market_full")` logger 通道，与 L0-L5 日志格式一致。
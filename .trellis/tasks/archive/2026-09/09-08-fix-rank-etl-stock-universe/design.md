# Design：修复 ranking ETL 白名单遗漏混合型

## 1. 架构与边界

```
┌─────────────────────────────────────────────────────────────────┐
│ Backend (backend/fund-select)                                   │
│                                                                  │
│  scheduler/tasks.py                                             │
│    ├─ refresh_configured_funds_sync (funds.yaml 债基)           │
│    │    └─ snapshot_fund(code, fetch_holdings=True)              │
│    │         # 默认 fetch_ranking=False → ranking 块跳过        │
│    │                                                             │
│    └─ refresh_stock_funds_sync (funds_stock.yaml)               │
│         └─ snapshot_fund(code, fetch_holdings=False,             │
│                           fetch_ranking=True)                   │
│              # 142 只全抓 ranking，含混合型                       │
└─────────────────────────────────────────────────────────────────┘
                            │ (后续重抓)
                            ▼
                   fund_achievement_rank 表
                   （混合型 42 只补齐到 142 只）
```

**边界**：
- 前端 0 改动（DTO 已支持，前端代码不需修改）。
- funds_stock.yaml / funds.yaml 名单不变。
- 债基 ETL 路径行为不变（仍不抓 ranking）。
- 仅改 refresh_service.py + scheduler/tasks.py + 测试。

## 2. 数据流

### 2.1 改动点 1：snapshot_fund 加 fetch_ranking 参数

```python
def snapshot_fund(
    code: str,
    mgr_worktime: dict[str, int],
    mgr_company: dict[str, str],
    today: pd.Timestamp | None = None,
    holdings_year: str | None = None,
    fetch_holdings: bool = True,
    fetch_ranking: bool = False,        # 新增参数
) -> dict:
    ...
    # 5. 业绩排名（由调用方 fetch_ranking 控制；债基路径默认 False 不抓）
    if fetch_ranking:
        try:
            ach_df = fetch_achievement(code)
            if not ach_df.empty:
                out["achievement"] = ach_df
                out["achievement_as_of_date"] = ref.date()
        except Exception as e:
            logger.warning("achievement_xq 失败 %s: %s", code, str(e)[:150])
```

### 2.2 改动点 2：调用方传参

```python
# refresh_configured_funds_sync（债基，不改）
snap = snapshot_fund(code, mgr_worktime, mgr_company)
# 默认 fetch_ranking=False，债基不抓 ranking ✓

# refresh_stock_funds_sync（stock，改）
snap = snapshot_fund(code, mgr_worktime, mgr_company, fetch_holdings=False, fetch_ranking=True)
# 142 只全抓 ranking ✓
```

### 2.3 测试覆盖

`_run_snapshot` 辅助函数扩展：

```python
def _run_snapshot(fund_type: str, fetch_holdings: bool = True,
                  fetch_ranking: bool = False, ...):
    """snapshot_fund 单测辅助：可控制 fetch_ranking 参数"""
    ...
```

新增 5 个测试用例：

```python
def test_stock_path_fetches_ranking_for_mixed_flexible():
    """混合型-灵活配置 + fetch_ranking=True → 调 fetch_achievement"""
    fetch_achievement_mock = ...
    _run_snapshot(fund_type="混合型-灵活配置", fetch_ranking=True)
    fetch_achievement_mock.assert_called_once()

# 其他 4 个类似
```

### 2.4 重抓流程

```
1. 改代码 → commit
2. 重启后端（应用新代码）
3. POST /api/funds/stock/refresh （不带 limit，全 142 只）
4. 轮询 GET /api/funds/stock/refresh/status?task_id=xxx
   看到 status=done + completed=142 即完成
5. 实测覆盖率：
   SELECT code FROM funds_stock_yaml
   WHERE ranking_count = 0;  -- 应为 0 或 ≤ 2
```

## 3. Trade-offs

| 决策 | 优点 | 代价 |
|---|---|---|
| 加 `fetch_ranking` 参数（方案 A） | 与 `fetch_holdings` 对称；调用方语义清晰；测试简单 | snapshot_fund 签名多 1 参（不影响 ABI 兼容性） |
| 不选"白名单配置化" | 用户决策明确；YAGNI | 后续若需精细控制（如"基金类型=纯债的不抓"），需重做 |
| 不选"独立 ranking ETL 步骤" | 改动大；与现有 snapshot 一致性弱 | 已选更简单的方案 A |
| 重抓 142 只全量 | 一次性补齐 42 只缺失；与"去掉白名单"语义一致 | 耗时 7-12 分钟 |
| 重抓仅 42 只缺失 | 耗时短 | 需要 ad-hoc SQL 脚本或新接口；破坏现有 refresh 流程的一致性 |

## 4. 兼容性 & 回滚

**兼容性**：
- snapshot_fund 签名新增可选参数 `fetch_ranking`，老调用方（只传旧参数）行为不变。
- 现有测试 `test_default_ignores_fund_type` 不动。
- 债基 ETL 路径行为不变（仍不抓 ranking）。
- 前端零改动。

**回滚步骤**：
1. snapshot_fund 签名删除 `fetch_ranking`，ranking 块加回 `if fund_type.startswith("股票型")...` 判断。
2. refresh_stock_funds_sync 调用 snapshot_fund 不传 fetch_ranking。
3. ranking 表数据不变（只多不删）。

## 5. 实施顺序

1. **refresh_service.py**：snapshot_fund 加 `fetch_ranking` 参数 + 改写 ranking 块。
2. **scheduler/tasks.py**：refresh_stock_funds_sync 调用 snapshot_fund 传 `fetch_ranking=True`；docstring 更新。
3. **tests/test_refresh_service.py**：扩展 `_run_snapshot` 加 `fetch_ranking` 参数；新增 5 个测试用例。
4. **本地验证**：`cd backend/fund-select && python -m pytest tests/ -v` 期望 176 passed。
5. **重启后端** + 触发 `POST /api/funds/stock/refresh`（142 只全量）。
6. **覆盖率验证**：SQL 查询 ranking 0 行数 ≤ 2；抽样 003598/002943/519195 HTTP 实测 ≥ 10 行。
7. **commit + archive**。

## 6. 风险与监控

- **风险 1**：snapshot_fund 漏改某个调用方 → grep `snapshot_fund` 调用点确认仅 2 处。
- **风险 2**：雪球频率限制 → 142 只 × ~3 秒 ≈ 7-12 分钟；现有 MAX_RETRY_PER_FUND=3 自动重试。
- **风险 3**：重抓过程中数据库锁定 → 每只立即 commit，单只失败不影响其它。
- **风险 4**：极少数基金雪球无 ranking → 容忍 ≤ 2 只 0 行；后续可单独 refresh。

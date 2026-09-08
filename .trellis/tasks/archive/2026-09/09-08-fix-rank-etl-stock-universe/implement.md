# Implement：修复 ranking ETL 白名单遗漏混合型

## 实施清单（按依赖顺序）

### Phase A：代码改动

- [ ] **A1**. `backend/fund-select/src/services/refresh_service.py`：
  - `snapshot_fund` 签名加 `fetch_ranking: bool = False`
  - 改写 ranking 块（line 97-106）：去掉 `fund_type` 判断，改为 `if fetch_ranking:`
  - 更新函数 docstring（顶部 + ranking 块注释）
- [ ] **A2**. `backend/fund-select/src/scheduler/tasks.py`：
  - `refresh_stock_funds_sync` 调用 snapshot_fund 时传 `fetch_ranking=True`
  - 函数 docstring 更新（去掉"仅股票型 + QDII"，改为"funds_stock.yaml 全名单"）

### Phase B：测试

- [ ] **B1**. `backend/fund-select/tests/test_refresh_service.py`：
  - `_run_snapshot` 辅助函数签名加 `fetch_ranking: bool = False`
  - 内部 `snapshot_fund` 调用传 fetch_ranking
- [ ] **B2**. 新增 5 个测试用例：
  - `test_stock_path_fetches_ranking_for_mixed_flexible`：fund_type="混合型-灵活配置" + fetch_ranking=True → fetch_achievement 调用 1 次
  - `test_stock_path_fetches_ranking_for_mixed_partial_equity`：fund_type="混合型-偏股" + fetch_ranking=True → 调用
  - `test_stock_path_fetches_ranking_for_stock_type`：fund_type="股票型-标准指数" + fetch_ranking=True → 调用（回归）
  - `test_stock_path_fetches_ranking_for_qdii`：fund_type="QDII" + fetch_ranking=True → 调用（回归）
  - `test_bond_path_skips_ranking_even_for_stock_typed_funds`：fund_type="股票型-标准指数" + fetch_ranking=False → **不**调用（债基路径误调用的回归保护）

### Phase C：本地验证

- [ ] **C1**. `cd backend/fund-select && python -m pytest tests/ -v` 期望 176 passed（171 + 5 新增）
- [ ] **C2**. `cd backend/fund-select && ruff check src/` 期望无新增警告

### Phase D：重抓数据

- [ ] **D1**. 重启后端（应用新代码）
  - Windows：`scripts\start-fund-select-dev.bat` 重启
- [ ] **D2**. 触发全量 stock refresh：
  ```bash
  curl -X POST "http://localhost:8095/api/funds/stock/refresh" -H "Content-Type: application/json"
  ```
  返回 `{"task_id": "...", "status": "started"}`
- [ ] **D3**. 轮询进度：
  ```bash
  curl "http://localhost:8095/api/funds/stock/refresh/status?task_id=<TASK_ID>"
  ```
  期望：`status=done, total=142, completed=142, failed≤5`
- [ ] **D4**. 等待 7-12 分钟（142 只 × ~3-5 秒/只）

### Phase E：覆盖率验证

- [ ] **E1**. SQL 验证 funds_stock.yaml 名单中 ranking 0 行数 ≤ 2：
  ```sql
  -- 等价 Python：
  from src.data.fund_universe import resolve_universe_codes
  codes = resolve_universe_codes('stock')
  active = {Fund.code where is_active}
  rank_count = {code: count rows in FundAchievementRank where code=code}
  zero_count = [c for c in active if rank_count.get(c, 0) == 0]
  assert len(zero_count) <= 2
  ```
- [ ] **E2**. 抽样 HTTP 验证：
  ```bash
  curl /api/funds/stock/003598 | jq '.achievement_ranks | length'  # ≥ 10
  curl /api/funds/stock/002943 | jq '.achievement_ranks | length'  # ≥ 10
  curl /api/funds/stock/519195 | jq '.achievement_ranks | length'  # ≥ 10
  ```

## 关键文件清单

| 文件 | 改动类型 |
|---|---|
| `backend/fund-select/src/services/refresh_service.py` | A1：snapshot_fund 加 fetch_ranking 参数 + 改 ranking 块 |
| `backend/fund-select/src/scheduler/tasks.py` | A2：refresh_stock_funds_sync 传 fetch_ranking=True |
| `backend/fund-select/tests/test_refresh_service.py` | B1-B2：扩展 _run_snapshot + 新增 5 测试 |

## 回滚点

- Phase A 失败：撤回 snapshot_fund 改动，ranking 块恢复 `if fund_type.startswith(...)`。
- Phase B 失败：测试加回 `if fetch_ranking:` 与 `if fund_type.startswith(...)` 的双保险（不推荐）。
- Phase D 失败（重抓有问题）：不重抓即可，业务逻辑已修复，下次自然刷新会补齐。

## 风险点（先验）

1. **调用方遗漏**：grep `snapshot_fund` 确认仅 2 处调用（refresh_configured_funds_sync + refresh_stock_funds_sync）。
2. **重抓耗时**：142 只 × ~3 秒 = 7-12 分钟；失败 3 次重试（MAX_RETRY_PER_FUND）。
3. **频率限制**：雪球无明确 QPS 文档，按经验 1 QPS 即可；如报错则下次刷新自动补齐。

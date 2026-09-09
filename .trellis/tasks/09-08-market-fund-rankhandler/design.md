# Design: market tab 接入东方财富 rankhandler 批量业绩接口

## 1. 范围与边界

### 在范围内

| 层 | 改动 |
|---|---|
| DB schema | 新增 `market_fund_rank` 表 |
| 后端 fetcher | 新增 `data/market_rank_fetcher.py`（rankhandler 包装） |
| 后端 refresh | 新增 `services/market_rank_refresh.py` |
| 后端 scheduler | `scheduler/tasks.py` 加 `refresh_market_rank_sync` |
| 后端 cron | `scheduler/manager.py` 加 06:35 任务 |
| 后端 service | `services/filter_service.py` `_screen` 加 LEFT JOIN market_fund_rank，`_to_dto` 优先从 market_fund_rank 读业绩；`universe_stats` 扩展 `with_performance` 统计 |
| 后端 API | `api/routes.py` 新增 `/discovery-{bond,stock}/rank/refresh` 端点 |
| 前端 API | `lib/api.ts` 加 `refreshRank()` |
| 前端 UI | `RefreshStatusPopover` 加「拉业绩」按钮 + 文案 |

### 不在范围内（保持原样）

- 老 yaml refresh 路径（funds.fund_type + fund_performance/fees/holdings/risk_metrics/benchmark/achievement_rank）
- `funds` 表的 size_yi / name / market_subtype / age_years / mgr_*（L0 + L2 阶段写入的数据）
- `_screen("bond"/"stock")` 老路径（仍走 yaml 名单 + LEFT JOIN FundPerformance）
- 现有 `discovery-*` 接口 URL（只是 SQL 加了一个 LEFT JOIN，DTO 字段不变）

### 兼容性

- 老接口 `GET /api/funds/discovery-{bond,stock}/screen` 返回结构兼容：`items[].ret_1y/3y/...` 字段存在但来源从 FundPerformance 切到 MarketFundRank
- 老 60 只 yaml 名单基金同时有 FundPerformance（详细：含 dd_3y / sharpe / ir / alpha）**和** MarketFundRank（最新业绩）—— DTO 优先 MarketFundRank，但 fund_performance 数据不丢
- 老 stock tab（funds_stock.yaml）SQL 不变，性能不受影响

### 09-09 探索更新

**原计划 L2 fund_basic 阶段被拆分为两部分**：

| 字段 | 原计划 | 新方案 |
|---|---|---|
| `fund_type` | L2 雪球单只拉 | **L0 用 `ak.fund_name_em()` 全量 5 秒** |
| `mgr_name / mgr_company / mgr_days / mgr_experience_years` | L2 雪球单只拉 | **L0 用 `ak.fund_manager_em()` 全量 30 秒** |
| `established_date / age_years / size_yi` | L2 雪球单只拉 | **L2 用东财移动端 `FundMNBasicInformation` 逐只，仅对 L1 预筛后 ~1573 只，10 分钟** |

理由：
- 雪球 `ak.fund_individual_basic_info_xq` 接口已 schema 残缺（`r.json()["data"]` 缺 key），29 只 C/E 份额拿不到
- 经理和基金分类本来就有全量接口（akshare 一把抓），没必要逐只拉
- size_yi / age_years 是低频字段，且逐只慢（0.4s/只），只对筛选后的小 universe 跑

## 2. 数据库 Schema

```sql
-- 新表：market_fund_rank
CREATE TABLE market_fund_rank (
  code VARCHAR(6) PRIMARY KEY,
  nav_date DATE,
  nav_latest FLOAT,
  ret_1w FLOAT, ret_1m FLOAT, ret_3m FLOAT,
  ret_6m FLOAT, ret_1y FLOAT, ret_2y FLOAT,
  ret_3y FLOAT, ret_ytd FLOAT, ret_all FLOAT,
  ft_code VARCHAR(8),
  updated_at DATETIME
);
```

启动时 SQLAlchemy `create_all` 自动建新表（幂等）。无需 ALTER。

## 3. 数据流

```
每日 06:35
  └─ scheduler.tasks.refresh_market_rank_sync()
       └─ market_rank_fetcher.fetch_market_rank_bulk(
              fts=["gp","hh","zs","qdii"],   # stock universe 对应 ft
              pages_per_ft=20,
              sd=today-3y, ed=today,
              sc="3nzf", st="desc")
            └─ 每页 HTTP 0.5s 延时
            └─ 解析 JSONP var rankData = {datas: [...], allRecords, allPages}
            └─ 单次 datas split(',') 取 [code, name, nav_date, nav_latest, ret_*, ft_code]
       └─ market_rank_refresh.refresh(session, df, task_id)
            └─ upsert market_fund_rank
            └─ 每 500 行 commit + 更新 RefreshRun 进度

用户访问 /funds/discovery-stock
  └─ useDiscoveryStockFundList → GET /api/funds/discovery-stock/screen
       └─ FilterService.screen_discovery_stock(...)
            └─ _screen("discovery-stock", ...)
                 └─ SELECT FROM funds
                      LEFT JOIN market_fund_rank ON fund.code = market_fund_rank.code
                      WHERE fund.is_active AND fund.market_subtype IN (stock_subtypes)
                 └─ DTO: ret_1y/3y/... 来自 MarketFundRank（LEFT JOIN 没数据则为 NULL）

用户点「拉业绩」按钮
  └─ RefreshStatusPopover → GET /api/funds/discovery-stock/rank/refresh
       └─ BackgroundTasks.add_task(refresh_market_rank_sync, preset_task_id)
       └─ 前端 1s 轮询 progress，弹窗显示进度
```

## 4. API 契约

### 新增端点

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/funds/discovery-bond/rank/refresh` | 触发债基·市场业绩 refresh |
| GET | `/api/funds/discovery-stock/rank/refresh` | 触发股基·市场业绩 refresh |

两个端点共用同一个 task 函数 `refresh_market_rank_sync`（一个 batch 拉两类 universe 的 ft）。

### Response

复用 `RefreshResponse`：
```json
{ "task_id": "uuid", "status": "started" }
```

### Progress 接口

复用现有 `RefreshStatusResponse`（从 `RefreshRun` 表读）。

### Screen 接口

URL / query / response 结构**不变**：
- 输入：`?market_type=股票型&min_age=3&...`（CSV market_types 是 akshare subtype）
- 输出：`{ total, items: [{ code, name, fund_type, size_yi, age_years, dd_3y, ret_1y, ret_3y, ret_5y, sharpe, ..., mgr_name, ... }] }`
- 变化：items[].ret_1y/3y 等业绩字段的**数据源**从 `fund_performance` 切到 `market_fund_rank`

## 5. 关键设计决策

### D1 数据源彻底分开
- yaml 名单：仍走 fund_individual_basic_info_xq 逐只 → 完整字段（含 fund_type 细分类 + dd_3y + sharpe + ir + alpha + holdings + fees + benchmark + achievement_rank）
- market 名单：L0 全量 akshare + L1 rankhandler 批量 + L2 东财 msm 单只 → fund_type / mgr_* / 业绩 + 规模/成立日期
- **两套实现不混用**：market 路径完全不调老 fund_basic fetcher / fetch_nav / fetch_fees / fetch_holdings / fetch_achievement

### D2 rankhandler ft 映射

| discovery tab | ft 列表 | 数量（实测） |
|---|---|---|
| discovery-bond | `["zq"]` | 4895 |
| discovery-stock | `["gp", "hh", "zs", "qdii"]` | gp=1085 + hh=8551 + zs=4530 + qdii=? |

**未覆盖的 universe 子类**：
- `Reits` / `REITs` → ft 应该是 `bb` 或类似；rankhandler 暂不支持完整覆盖
- `QDII-FOF`、`QDII-REITs` 等 → QDII ft 包含，但具体子分类需 ft 列表细查

**简化**：先用标准 5 类（gp/hh/zq/zs/qdii）拉取，Reits 单独处理或忽略（Reits 不在主 universe）。

### D3 upsert 策略

```python
# refresh_market_rank_refresh.refresh()
for batch in chunks(df, 500):
    codes = batch['code'].tolist()
    existing = set(session.execute(
        select(MarketFundRank.code).where(MarketFundRank.code.in_(codes))
    ).scalars().all())
    now = datetime.now(UTC)
    for row in batch.itertuples():
        if row.code in existing:
            session.execute(
                update(MarketFundRank).where(MarketFundRank.code == row.code)
                .values(nav_date=..., nav_latest=..., ret_1w=..., ..., ft_code=..., updated_at=now)
            )
        else:
            session.add(MarketFundRank(code=row.code, ..., updated_at=now))
    session.commit()
```

每 500 行 commit（防 SQLite lock），进度实时写 RefreshRun。

### D4 DTO 字段优先级

`_to_dto()` 修改（仅影响 discovery-* tab）：

```python
@staticmethod
def _to_dto(f, p, fee, hold, risk, market_rank, ach_for_code):
    # 业绩字段：优先 market_rank（最新），fallback 到 fund_performance（详细）
    # 但 discovery-* tab 的 SQL 不再 LEFT JOIN fund_performance，p 始终为 None
    ret_1y = market_rank.ret_1y if market_rank else None,
    ret_3y = market_rank.ret_3y if market_rank else None,
    ret_1m = market_rank.ret_1m if market_rank else None,
    ...
```

**注意**：discovery-* tab 不需要 fund_performance 的 `ret_5y`（rankhandler 没有 `ret_5y`，但有 `ret_2y / ret_3y`）。`ret_5y` 字段在 discovery tab DTO 中保持 NULL（或新增 `ret_2y / ret_3y` 字段）。

**决策**：`ret_5y` 字段在 discovery tab 显示 NULL（标 -）；`ret_1y / ret_3y` 是核心指标，已填充。

### D5 scheduler 时序

```
06:30 daily_market_universe_refresh  (已有 — ak.fund_name_em → upsert funds.name/market_subtype)
06:35 daily_market_rank_refresh        (新增 — rankhandler 批量 → upsert market_fund_rank)
07:05 daily_fund_refresh               (已有 — yaml 名单 → snapshot_fund 5 fetcher)
```

### D6 前端双按钮

`RefreshStatusPopover` 改造：
```typescript
interface RefreshStatusPopoverProps {
  refreshUrl?: string;          // 名单 refresh（已有）
  refreshRankUrl?: string;       // 业绩 refresh（新增）
  ...
}

return (
  <div>
    <button onClick={...}>刷新名单</button>
    <button onClick={refreshRank}>拉业绩</button>
    {status && <ProgressBar ... />}
  </div>
);
```

或者更简洁：保留现有「立即刷新」按钮，新增第二个「拉业绩」按钮，**两个按钮并列**。

## 6. 前端契约

### RefreshStatusPopover

```typescript
interface RefreshStatusPopoverProps {
  refreshUrl?: string;          // /funds/api/funds/discovery-stock/refresh
  refreshRankUrl?: string;      // /funds/api/funds/discovery-stock/rank/refresh（新增）
  statusUrl?: string;
  statusRankUrl?: string;       // 同 refreshRankUrl + /status（新增）
  onRefreshed?: () => void;     // 业绩跑完回调
}
```

### FundsHeader

```typescript
export function FundsHeader({ active, total, ..., exportKind, ... }) {
  ...
  const refreshUrl = REFRESH_URL[exportKind];            // 名单
  const refreshRankUrl = REFRESH_RANK_URL[exportKind];   // 业绩
  ...
  <RefreshStatusPopover
    refreshUrl={refreshUrl}
    refreshRankUrl={refreshRankUrl}
    statusUrl={refreshUrl ? `${refreshUrl}/status` : undefined}
    statusRankUrl={refreshRankUrl ? `${refreshRankUrl}/status` : undefined}
    onRefreshed={onRefreshed}
  />
}
```

## 7. 性能预估

| 阶段 | 数据量 | 耗时 |
|---|---|---|
| rankhandler 单页 | 50 只 | ~0.5s（含 0.5s 延时） |
| stock universe | 4 ft × 20 页 = 80 页 | ~40s |
| bond universe | 1 ft × 20 页 = 20 页 | ~10s |
| **总耗时** | 100 页 × 50 只 = 5000 只 | **~50s** |
| upsert（每 500 行 commit） | 10 批 commit | < 5s |
| **总计** | — | **~55s** |

vs 现状（什么都不做）：0s 但无数据
vs 旧方案（逐只 fetch_basic+nav）：~12 小时

## 8. 测试策略

### 单元测试

```python
# tests/test_market_rank_fetcher.py
def test_fetch_market_rank_page_parses_jsonp(): ...   # mock response
def test_fetch_market_rank_bulk_pages_through_ft(): ...
def test_handles_rankhandler_error(): ...

# tests/test_market_rank_refresh.py
def test_insert_new_rank(): ...
def test_update_existing_rank_overwrites(): ...
def test_does_not_touch_fund_performance(): ...        # 关键回归

# tests/test_discovery_filter_service.py
def test_screen_uses_market_rank_for_returns(): ...    # 业绩来自 market_fund_rank
def test_screen_falls_back_when_no_market_rank(): ...  # 没数据时 ret 字段为 NULL
def test_universe_stats_counts_with_performance(): ...
```

### 手工验证

```bash
curl -s 'http://localhost:8095/api/funds/discovery-stock/screen' | jq '.items[0]'
# 应包含 ret_1y / ret_3y 等非 NULL 字段

curl -s 'http://localhost:8095/api/funds/discovery-bond/screen?min_size_yi=10&sort=ret_3y&order=desc' | jq '.items[0]'
```

## 9. Rollback

| 阶段 | 回滚 |
|---|---|
| Schema | 删 market_fund_rank 表（不影响其他表） |
| Fetcher / refresh | 删文件 |
| Scheduler | 移除 06:35 cron |
| API | 移除 /rank/refresh 端点 |
| _screen | 改回只 LEFT JOIN FundPerformance（业绩全 NULL，但 SQL 兼容） |
| 前端 | 不传 refreshRankUrl |

无破坏性变更；最坏情况是回滚到"无业绩"现状。

# fund-select 契约（API / DB / 缓存 / 前后端链路）

## 每周自动刷新（2026-10-29）

- `src/scheduler/scheduler.json` 定义四项独立周任务：`weekly_bond_refresh` 07:05、`weekly_stock_refresh` 08:05、`weekly_discovery_bond_refresh` 09:05、`weekly_discovery_stock_refresh` 10:05；每周六，显式 `Asia/Shanghai`。`cron_human` 与 cron 保持一致，由真实 CronTrigger 下一次日期测试约束。
- `refresh_tab_sync` 仅调用该 tab 的采集器。配置名单 `use_cache=False`；市场 bond/stock profile 默认预筛收益 10%/20%，规模5亿、经理5年，类型复用 `market_subtype_map`。
- 每任务独立运行标记、当前快照、上次结果和历史；同任务 cron/立即执行重复触发409/跳过；不同任务共用 asyncio.Lock 排队，不因上一项超时尚未完成而丢弃本周任务。已排队状态为 queued，采集线程启动后变 running。
- 采集经 `asyncio.to_thread`；每项 `max_instances=1`、`coalesce=True`、错过触发宽限3600秒。MemoryJobStore 不补跑停机期间历史周次。生产保持单 uvicorn worker。
- success/partial/failed 分类检查 `stage_results.*.status` 与嵌套 `result.failed`，兼容 completed/inserted/updated，空名单失败。某任务失败不影响队列后续任务。
- 各项开始/结束时间带 `+08:00`，结果/错误追加至 `data/scheduler/weekly_refresh.jsonl`；NAS data volume持久化。读取时按job_id隔离；旧 `weekly_fund_refresh` 或无job_id的组记录按items.tab投影成单任务状态与时间，不能把整组partial传播给成功tab。
- 四 tab 共用顶部右侧齿轮打开 `SchedulerDialog`，原生dialog提供模态/键盘约束，关闭恢复焦点/滚动；仅弹框打开时5秒轮询。旧 `/funds/scheduler` 重定向 `/bond?scheduler=1` 自动打开弹框。API路径不变：GET `/api/funds/scheduler/jobs`、PATCH `/jobs/{id}`、POST `/jobs/{id}/run`、GET `/jobs/{id}/runs?limit=20`；404/409/503与limit1..200约束保留，Next代理GET/PATCH/POST。
- 启停覆盖原子保存至 `data/scheduler/settings.json`，重启后读取，禁止写镜像源配置。禁用仅暂停自动任务，不中止当前执行，允许立即执行。
- 旧设置 `weekly_fund_refresh=false` 迁移为四项默认暂停；新任务显式设置优先。保存时写四项独立enabled，重启保持。线程进度快照加锁；互斥不涵盖四tab原来的单独刷新入口。
- 历史最新在前，损坏行跳过，每项最近20次；操作错误不被轮询清掉。
- `test_weekly_refresh.py` / `test_scheduler_management.py` 覆盖四项时间、仅采集对应tab、独立设置/历史、旧数据迁移、排队无重叠、失败释放队列及线程执行。

## 1. Scope / Trigger

- 任务 09-01-fund-select-v1-bond：新增跨层契约（FastAPI ↔ Next.js 代理 ↔ 前端表格/对比），且补回了预研缺失的费率 fetcher 契约。
- 任务 09-09-fund-select-pagination：分页契约（server 端排序-切片、total/limit 不变量）。
- 任务 09-09-fund-list-rank：同类排名 DTO（RankPercentile 三字段 + Pydantic 静默砍字段陷阱）。
- 任务 09-10-qdii-reits-coarse-mapping / 09-10-subtype-coverage-fix / 09-10-fund-table-type-chip：粗类别映射契约的完整化与边界。
- 任务 09-11-bond-market-type-fix：粗类别映射契约的**前端一致性**强化（chip 文案 derive + 死选项清理 + 跨 tab 透传），沉淀于 §8a–§8d。
- 任务 09-11-bond-full-refresh-default-10pct：债基/股基全量刷新预筛默认必须拆开（`min_ret_3y` 10 vs 20），沉淀于 §11。
- 任务 09-11-bond-detail-fees-holdings-writeback：market_full_pipeline 加 `pipeline_profile` + L6_fees_holdings 阶段；债基详情页自给自足（复用 fetch_fees/fetch_bond_hold/persist_snapshot），沉淀于 §12。

## 2. Signatures

### API（前缀 /api/funds，全部 GET）

| 路由 | 参数 | 返回 | 错误 |
|---|---|---|---|
| /health | - | `{status:"ok"}` | - |
| /screen | min_age, min_size_yi, max_dd_3y, min_mgr_exp（均可空）; sort; order; exclude_qdii（默认 false）; **page**（默认 1, ≥1）; **limit**（默认 50, 1-200） | `{total, items:[FundListItem]}` **total=筛后总数；items=当页** | sort 不在白名单→422；page<1 / limit<1 / limit>200 → 422 |
| /stock/screen | min_age, min_size_yi, max_dd_3y, min_mgr_exp, min_sharpe（股票独有）; sort; order; exclude_qdii; **page, limit** | 同 /screen | 同 /screen |
| /discovery-bond/screen | min_age, min_size_yi, max_dd_3y, min_mgr_exp, min_sharpe, min_ret_1y, min_ret_3y, max_nav_stale_days; market_types（akshare 粗类别，可空）; sort; order; exclude_qdii; **page, limit** | 同 /screen | 同 /screen |
| /discovery-stock/screen | 同 /discovery-bond/screen | 同 /screen | 同 /screen |
| /{code} | - | FundDetail（业绩+fees+holdings） | 404 |
| /refresh | limit 可空 | `{task_id, status:"started"}`（BackgroundTasks） | - |
| /refresh/status | task_id 可空（空=最近一次） | `{task_id,status,total,completed,failed,errors[]}` | 404 无记录 |
| /export/csv | 同 screen | text/csv + UTF-8 BOM + `filename=funds_YYYYMMDD.csv` | - |
| /stats | - | `{total,with_performance,with_fees,with_holdings,last_refresh_at}` | - |

### 分页契约（09-09-fund-select-pagination）

**核心不变量**：

- `total` 永远是**筛后命中总数**，与 page / limit 无关。前端用它算总页数 `Math.ceil(total/limit)`。
- `items` 长度 ≤ `limit`，可能为空（`page` 越界时）。
- `total` 与 `items` 的关系：`items ⊂ 全量items；total = len(全量items)`。多页之间无重叠、无遗漏（按当前 sort 排序后切片）。

**服务端排序-切片顺序（关键）**：

```python
# 1. SQL JOIN 取全量 rows
rows = self.db.execute(q).all()
# 2. ach_map 仍按全量 codes 查（保证排序前数据完整，rank 字段不丢）
codes = [f.code for f, *_ in rows]
ach_rows = self.db.execute(select(...).where(FundAchievementRank.code.in_(codes))).all()
# 3. 组装全量 items
items = [_to_dto(f, p, fee, hold, risk, market_rank, ach_map.get(f.code)) for f, p, fee, hold, risk, market_rank in rows]
total = len(items)
# 4. Python in-memory 排序（None 永远排末位）
valued = [it for it in items if getter(it) is not None]
valued.sort(key=getter, reverse=descending)
empty = [it for it in items if getter(it) is None]
ordered = valued + empty
# 5. ★ 切片在排序之后
offset = (page - 1) * limit
items_page = ordered[offset : offset + limit]
return {"total": total, "items": items_page}
```

**为什么不在 SQL 层 ORDER BY + LIMIT/OFFSET**：

- 现状：discovery-stock universe ~4500 只 → Python `list.sort` < 100ms，深页 offset 切片 O(N) 但仍 < 1s
- 风险：5000→5w+ 时再切 SQL。当前不做是为避免 SQL 注入白名单、LEFT JOIN 多表、ach_map 二次查询的复杂改造
- 触发再切的条件：universe > 5w 或 P95 > 1s

**与 FundAchievementRank 的关系**：

`ach_map` 查询用 `codes = [f.code for f, *_ in rows]`，是**排序前**的全量 codes。排序-切片不会影响 rank 字段正确性（每页 DTO 内 rank_* 都来自同一份 ach_map）。

**前端 URL 同步**（`useFilters` / `parseFiltersFromSearch` / `filtersToSearch`）：

| URL 参数 | 写入条件 | 默认 |
|---|---|---|
| `page` | `page > 1` | 1 |
| `limit` | `limit !== 50` | 50 |

**筛选 vs 排序 对 page 的影响**：

| 触发 | page 重置？ |
|---|---|
| numeric 维度 / exclude_qdii / market_types 变化 | ✅ 重置 page=1 |
| sort 字段 / order 变化 | ❌ 保持 page |
| setLimit | ✅ 重置 page=1 |
| clearAll | ✅ 重置 page=1（合理：清空筛选后命中集变了，原 page 没意义） |

**前端状态归属**：`page` / `limit` 是 `FundFilters` 的字段，跟其它 numeric 维度一起序列化/反序列化、一起触发 useEffect 重拉。不另起 state，避免 URL / 状态双源。

**`LIMIT_OPTIONS = [25, 50, 100] as const`** 导出在 `apps/fund-select/src/lib/types.ts`，Pagination 组件直接复用，不硬编码。

**Performance budget**：discovery-bond 全 universe（~500 只）page=1, limit=50 → 后端 P95 < 800ms（含 DB JOIN × 5 + Python sort + 4 周期排名查询）；前端首屏 < 1.5s。

### 关键语义

- **dd_3y 库内为负值**（如 -4.47）。用户阈值 `max_dd_3y=5` 按**绝对值**比较：SQL 用 `dd_3y >= -abs(max_dd_3y)`。前端展示原值（负号保留）。
- **fee_annual 是计算字段**：`fee_mgmt + fee_custody + (fee_service or 0)`；任一主字段缺失返回 null（不是 0）。
- **筛选宇宙按 yaml 切分**，再 ∩ `is_active==True`：
  - `/screen`、`/export/csv`、`/stats` → `config/funds.yaml`
  - `/stock/screen`、`/stock/export/csv`、`/stock/stats` → `config/funds_stock.yaml`
  - **yaml 名单阶段不要用 `fund_type LIKE` 当成员判定**（名单已分宇宙；`fund_type` 只展示）。
  - **全市场扫描（未做）** 再启用 `fund_type` 收口（股票型 / QDII / 混合型 vs 债券型）。
  - 详情 `/{code}`、`/stock/{code}` 仍按 code 查库，不按宇宙 404。
- **排除 QDII 是用户筛选 overlay**（`exclude_qdii=true`）：丢掉 `fund_type LIKE 'QDII%'` 或 `fund_type == '互认基金'`；`fund_type` 为 NULL 的保留。默认关闭，yaml 里的 QDII 仍显示。债基 `/screen`、`/export/csv` 与股票 `/stock/screen`、`/stock/export/csv` 都支持。
- 不按债券类型过滤（31 只含混合/QDII 照常展示）。
- FundPerformance 用 **LEFT JOIN**：无业绩记录的基金保留在筛选结果（业绩列显示 null → 前端 "-"）。
- **min_sharpe 仅股票 tab（09-04-stock-fund-sharpe-filter）**：`/stock/screen?min_sharpe=X` → `sharpe >= X`；sharpe 为 NULL（benchmark 不可用/样本不足，见 fund_risk_metrics 语义）的基金被一并排除，与 dd_3y 筛选惯例一致。前端 `STOCK_DEFAULT_FILTERS.min_sharpe = 0.8`（股票宇宙分布：中位 0.73 / p75 0.90，默认结果 142→53 只；叠加四维默认〔回撤 30〕后 25 只）；债基 `DEFAULT_FILTERS.min_sharpe = null` 且侧栏不渲染该项（`FilterPanel dimensions` prop 默认四维，股票页传 `STOCK_DIMENSIONS` 五维）。

### ORM（src/db/models.py）

- `funds`：code PK；age_years/size_yi/mgr_experience_years（Float 可空）；is_active 默认 True
- `fund_performance`：code PK；ret_1m/6m/1y/3y/5y + **dd_1y/3y/5y**（只有这三档回撤，无 dd_1m/dd_6m——performance_service 显式过滤）
- `fund_fees`：8 字段对齐预研 `cache/fees_{code}.json` 契约
- `fund_holdings_bond`：(code, report_date) 复合 PK。**只由债基 refresh 写入**：`snapshot_fund(fetch_holdings=True)`（债基路径默认）；股票 refresh 传 `fetch_holdings=False` 完全跳过季报拉取，不发 zqcc 请求。跳过逻辑按宇宙开关，不按 `fund_type` 猜（fund_type 短路已删）。

### 风险指标口径（fund_risk_metrics，risk_service.py）

- r_p 用 `fetch_nav` 的**日增长率/100**（东财复权口径，分红日已调整）。**陷阱**：不要用「累计净值」pct_change——它是 `单位净值+历史分红` 的简单加总（非复权），历史有分红的基金（库内 11/143 只）全序列被稀释：673010 实证 3 年 cum_p 63.4%（稀释）vs 98.8%（真复权），超额3y 46% → 81%。`fetch_nav_accumulated` 已因此删除。
- r_b = benchmark TRI pct_change（tri=NULL 的 QDII/互认基金：sharpe 有值、基准相关 4 指标 None）；r_f = risk_free_rate 表年化小数 /252 折日频。
- 窗口 = 近 3 年自然日；r_p∩r_b inner join，实际窗口尾日受 TRI 尾日约束（可能比净值尾日早一天，`as_of_date` 存的是刷新日）。样本下限 250 天。
- α = T-M 回归截距 ×252 简单年化；γ = 日频二次项系数（不年化、无量纲）；α-IR = α_d/σ_e×√252；夏普/IR = 日均超额/std×√252；excess_3y = 连乘累计算术差。
- `refresh_runs`：task_id PK，进度轮询数据源

### 基准 TRI 合成契约（fetch_benchmark_tri，benchmark_fetcher.py）

多成分基准（公式 N 个指数 + 存款）**必须按价格对齐，禁止对日收益 ffill**（任务 09-04-benchmark-price-align）：

```
成分存 close（index 与 unknown→fallback 分支都是）
→ 并集日历 reindex → ffill 价格 → dropna()（裁掉最晚成分上市前的前导行）
→ pct_change().fillna(0)   # 缺席交易日价格不变 → 收益 0，不复制前日收益
→ weighted = Σ ret×(w/total_w)；deposit 成分 = PBOC_DEPOSIT_FLOOR_RATE/252 常数铺满
→ tri = (1+weighted).cumprod() × 1000；source 标记不变
```

**source 枚举**（`fund_benchmark.source`，同 models.py 注释）：`fetched` / `partial:fallback:<sym>` / `fallback_chain:<sym>` / `unavailable:no_field` / `unavailable:basic_failed` / `unavailable:exhausted` / `unavailable:unknown_majority` / `skipped:qdii`。

**parse_formula 语义**（09-04-benchmark-yaml-coverage 扩充）：

- 乘号归一：`×`/`＊` translate；半角 `x` **仅在后跟数字时**视为乘号（`x(?=\d)`）——「收益率x60%」是乘号、「Index」内 x 是字母，一律 translate 会把英文名拆碎成 weight=0 的 unknown。
- 裸 `N%` 成分（公式末尾 `＋1%` 无指数名）→ `Component(name='存款加成', kind='deposit_floor')` 常数日收益 N%/252，不打「无法解析权重」warning。
- 剥离嵌套括号后残留的孤立 `(`/`)` 一并清除（非贪婪 `\(.*?\)` 只能剥一层）。
- `_PREFIXES` 含「人民币计价的」「经汇率调整的（后）」等实测语料前缀。

**高权重 unknown 置 NULL（R4，宁缺毋错）**：unknown 成分 weight ≥ 0.5 时**不**用 fallback 指数顶替，返回空 TRI + `source=unavailable:unknown_majority`（risk_service 对 tri=NULL 行取不到 r_b → 4 指标 None，不抛错）；weight < 0.5 维持 fallback 顶替 + `partial:fallback` 标记。

**Why**：A/HK/美/中债交易日历互不重合（港股佛诞、美股感恩节等）。对收益 ffill 会把成分缺席日的前一日收益**再计一次**，混合日历 3 年虚高 13.5pp（004316：真 +21.8% 算成 +35.3%），excess/IR/α 全歪。单成分基准两算法等价（回归测试锁定）。

**B1（已修复，09-04-fix-bond-index-date-shift）**：旧源 `bond_composite_index_cbond`（中债综合指数 财富/总值）返回日期整体 **−1 天**（真实周一标成周日、周五标成周四；2026-09-04 复测 3 年分布 Sun=142/Sat=11/Fri=9，与 A 股日历重叠 580/746；+1 天后 725/746，剩余 20 个周末行全部是债市调休交易日——股市休市、银行间开市，属正常）。中债成分收益落在错位日期上，inner join 丢周末行 → 中债周五收益永久丢失。**修复 = 换源非 shift**：`bond_index_general_cbond(index_category="综合指数", indicator="财富", period="总值")` 与旧源全史 6171 行逐值 **0 差值**（同一指数序列）、日期正确、还多最新一天；不做 +1 天 hack（源若日后自行修正会反向错位）。yaml `中债综合财富.source` 已改，ak_symbol 仍为 CBA00301。注意：中债日历含约 20 天/3 年的调休周六日，与 A 股指数并集合成时这些行股指数贡献 0、债指数贡献真实收益，是正确行为。
- **B1.2（已迁移，09-09-fix-pre-existing-pytest）**：akshare 1.18.39 移除 `bond_index_general_cbond` API（refresh 命中即 AttributeError）。迁到 `bond_new_composite_index_cbond()`（无需参数，默认全序列，返回 `[date, value]`）。该源**本身无 B1 错位 bug**：2026-09-09 实证 6174 行 / 近 3 年 weekday 分布 Sun=11 / Sat=9 调休 / Mon-Fri=144-149（与 B1 bug 实证的 Sun=142/Sat=11/Fri=9 截然不同）。yaml `中债综合财富.source` 同步更新为 `bond_new_composite_index_cbond`，生产 refresh 路径不再 AttributeError。
- **B3（已修复，09-04-benchmark-yaml-coverage）**：unknown 成分被 fallback 指数（中证800）**静默替换**、指标照算（006373 85% 权重被换，excess_3y=+146% 失真）→ 已按上方「高权重 unknown 置 NULL」语义修复，并补录 20 个 yaml 指数（中证官网 `stock_zh_index_hist_csindex` / 申万 `index_hist_sw` / 国证 `index_hist_cni`，收录标准=拉到日线且末条距今 ≤10 天）+ curated aliases。重刷实证：unknown 主成分被顶替 45→14 只（剩余均为确认无源无替代的海外指数，走置 NULL）、`partial:fallback` 9→0 行。

**Tests**（test_benchmark_fetcher.py）：mixed_calendar_no_return_duplication（双计消除）/ leading_dates_trimmed（前导裁剪）/ same_calendar_matches_return_compound（回归）/ deposit_weight_normalization / major_unknown_component_returns_null（R4 置 NULL，断言完全不发起指数拉取）/ bare_percent_addon_compounds_as_deposit（裸 N% 加成）/ half_width_x_is_mul_only_before_digit（乘号规则）/ cbond_uses_general_source + cbond_source_dates_kept_as_is（B1 换源后日期原样透传，周五行保留、无周日错位行）。

```python
# Wrong: 对收益 ffill —— B 缺席日复制前日收益（3年 +13.5pp）
ret_df = pd.DataFrame({k: s_return for ...}).sort_index().ffill().fillna(0)
# Correct: 对价格 ffill 后统一重算
px = pd.DataFrame({k: s_close for ...}).sort_index().ffill().dropna()
rets = px.pct_change().fillna(0)
```

## 3. 费率缓存契约（补回的 fetcher）

```
cache/fees_{code}.json = {
  "fee_buy_small": "0.8",       # 申购小额档（%）
  "fee_redeem_lt7d": "1.5",     # <7天
  "fee_redeem_7d_1y": "0.1",    # 7天~1年
  "fee_redeem_ge1y": "0.0",     # ≥1年
  "fee_mgmt": "0.3",            # 管理费/年
  "fee_custody": "0.1",         # 托管费/年
  "fee_service": 缺省           # C 类才有
}
```
- 值是**字符串数字**，fetch_fees 读时转 float；缺字段=无该项
- 联网重拉走东财 `fundf10.eastmoney.com/jjfl_{code}.html` 正则解析，31 份预研缓存优先命中

## 3a. 同类排名契约（fund_achievement_rank → FundListItem.rank_*）

`_parse_peer_rank(value: str | None) -> dict | None` 把数据库 `fund_achievement_rank.peer_rank`（格式 `'<rank>/<total>'`，如 `'25/204'`）解析成 DTO 字段：

```python
{"pct": round(rank / total * 100, 1), "total": total, "rank": rank}
```

**字段语义**（09-08-stock-fund-list-rank 引入 `rank` 字段，向后兼容）：
- `pct`：当前排名 ÷ 同类总数 × 100，保留 1 位小数（**前 X.X%** 展示用）
- `total`：同类总数（**分母**）
- `rank`：当前排名（**分子**，新增；旧后端不返回时前端 `rank=null` 不渲染分子段）

**边界行为**（验证过）：
| 输入 | 返回 |
|---|---|
| `'25/204'` | `{'pct': 12.3, 'total': 204, 'rank': 25}` |
| `'1694/5606'` | `{'pct': 30.2, 'total': 5606, 'rank': 1694}` |
| `'invalid'` / `''` / `None` | `None` |
| `'25'`（无斜杠） | `None` |
| `'0/100'` | `None`（rank ≤ 0） |
| `'200/100'` | `None`（rank > total） |
| 任何 ValueError/TypeError | `None`（不抛异常） |

**4 个排名口径**（`filter_service.RANK_PERIODS`）：
- `(年度业绩, 今年以来)` → `rank_ytd`
- `(阶段业绩, 近1年)` → `rank_1y`
- `(阶段业绩, 近3年)` → `rank_3y`
- `(阶段业绩, 近5年)` → `rank_5y`

**债基 tab 永远返回 `None`**（无入库数据）；`_screen("bond"/"discovery-bond")` 路径不查 `fund_achievement_rank`，DTO 字段是 null。

**DTO 字段类型**（前后端契约，`apps/fund-select/src/lib/types.ts`）：
```ts
export interface RankPercentile {
  pct: number | null;
  total: number | null;
  rank: number | null;  // 09-08-stock-fund-list-rank 新增
}
```

**前端消费模式**（双行列表展示）：
```tsx
{fund.rank_1y?.pct != null && <span>前 {fund.rank_1y.pct.toFixed(1)}%</span>}
{fund.rank_1y?.rank != null && fund.rank_1y?.total != null && (
  <span>· {fund.rank_1y.rank}/{fund.rank_1y.total}</span>
)}
```
`rank === null` 时仅显示"前 X.X%"，分子段不渲染——向后兼容旧后端。

**⚠️ 隐式契约：`src/api/models.py:FundListItem` 必须同步声明新字段**

`/screen` 端点的 `response_model=ScreenResponse → items: list[FundListItem]` 用 Pydantic v2 严格序列化——`_to_dto` 返回 dict 里**任何不在 `FundListItem` 模型里定义的字段都会被静默丢弃**（不报错、不警告）。所以后端在 `_to_dto` 加新字段时，**必须同时**给 `models.FundListItem` 补 Optional 字段，否则前端永远拿不到。

09-09 实战踩坑：`mr_*`（L1 业绩 11 字段）+ `rank_ytd/1y/3y/5y`（4 字段）=_to_dto 早就有，response 一律不见。原因就是 `models.FundListItem` 没补。修复 = 在 `models.py` 加 `RankPercentileDTO` 嵌套 + 14 个 Optional 字段。

**新增 list-item 字段 checklist**（加字段时 3 处必须同步）：
1. `services/filter_service.py:_to_dto` — 加进 return dict（**ranks 走 `**ranks` 展开**）
2. `api/models.py:FundListItem` — Pydantic 字段声明（**否则被静默砍掉**）
3. `apps/fund-select/src/lib/types.ts:FundListItem` — TS 接口同步

## 4. 前后端链路（basePath 陷阱）

```
浏览器 → http://localhost:3005/funds            (Next.js, basePath=/funds)
       → /funds/api/funds/*                     (app/api/funds/[...path]/route.ts 代理)
       → http://localhost:8095/api/funds/*      (FastAPI)
```

### Common Mistake: basePath 双前缀

**Symptom**: URL 变成 `/funds/funds`
**Cause**: page 放在 `app/funds/page.tsx` 且 basePath 也是 `/funds` → 实际路由 = basePath + 目录 = 双前缀；且 `redirect('/funds')` 会再叠一层
**Fix**:
- page 放 `app/page.tsx` 根（basePath 承担前缀）
- `router.push` / `<Link href>` 用**相对 basePath 的路径**（`/` → `/funds`，`/stock` → `/funds/stock`）；写 `href="/funds"` 会被拼成 `/funds/funds`
- 同步筛选 URL 只用 `?qs`，不要拼 `location.pathname`（浏览器 pathname 已含 `/funds`，`router.push('/funds?cleared=1')` 同样会变成 `/funds/funds?cleared=1`）
- 原生 `fetch('/funds/api/...')` **必须写全路径**——fetch 不吃 basePath

### Gotcha: 代理剥 BOM

代理 route 用 `res.text()` 会吞掉 CSV 的 UTF-8 BOM（TextDecoder 默认去 BOM）。**用 `res.arrayBuffer()` 二进制透传**。

## 5. Good/Base/Bad Cases

- Good: `GET /screen?max_dd_3y=5` 返回 dd_3y∈[-5,0] 的基金
- Good: `GET /discovery-stock/screen?page=2&limit=50&sort=ret_3y&order=desc` 返回 `items[50..99]`；`total` = 全量筛后命中数；与 page=1 无重叠
- Good: `GET /bond/screen?page=1&limit=50` 返回 31 只全量（total=31，items 长度=31，债基 tab 不显示分页器）
- Base: `GET /screen` 无参 → `funds.yaml` ∩ is_active（约 31 只）；分页默认 page=1, limit=50
- Base: `GET /screen?page=1`（URL 不带 limit）→ limit=50
- Bad: `GET /screen?sort=name` → 422（白名单外）；`GET /999999` → 404
- Bad: `GET /screen?page=0` / `?limit=0` / `?limit=1000` → 422
- Bad: `GET /screen?page=999` 越界 → 200 + `items=[]`，`total` 不变（前端分页器下一页按钮 disabled）
- Bad: 假设 `len(items) == total` —— 那是改造前的契约，引入分页后 `len(items) == min(limit, total - offset)`

## 6. Tests Required

`backend/tests/`（含交叉泄漏回归）：
- `test_filter_service.py`：四维组合/边界/排序/LEFT JOIN 保留/is_active 排除 + **TestPagination**（默认/单页/跨页不重叠/越界空/total 不受 page 影响/None 排序尾部）
- `test_stock_filter_service.py`：股票 tab 测试 + **TestStockPagination**
- `test_discovery_filter_service.py`：discovery 路径 SQL LEFT JOIN market_fund_rank + 业绩字段来源 + `_parse_peer_rank` 解析边界（25/204 / invalid / 0/100 / 200/100 全返 None）+ **TestDiscoveryPagination**（discovery-bond + discovery-stock）
- `test_universe_isolation.py`：债基/股票 yaml 宇宙互不泄漏；`fund_type` 不是成员谓词
- `test_performance_service.py`：回撤算法（1.0→1.2→0.9 = -25%）/收益窗口/None 语义
- `test_api.py`：TestClient + in-memory 覆盖依赖；422/404/BOM；stats 按宇宙计数 + **TestScreenPagination422**（page=0/limit=0/limit=1000/page=-1/limit=-1 全 422）
- `test_data_fetchers.py`：31 份费率夹具契约、债券分类关键词、yaml 宇宙

**分页测试夹具**：filter_service 用 `monkeypatch.setattr("src.data.fund_universe.load_fund_codes", ...)` 让 universe 包含 seed codes（避免依赖 yaml 实际 31 只名单）；discovery 测试 seed 同 `market_subtype` 让默认 universe 自动选中。

**测试夹具注意**：in-memory SQLite + TestClient 必须用 `StaticPool`（单连接共享），否则 TestClient 线程看不到建表。

## 7. Wrong vs Correct

### Wrong
```python
q.filter(FundPerformance.dd_3y <= max_dd_3y)   # 库内负值，-4.47 <= 5 恒真，筛不掉
q.where(Fund.is_active == True)                # 债基 tab 会看到股票 refresh 写入的全部活跃基金
Fund.fund_type.like("股票型-%")                # 股票 tab 会吃到债基名单里的混合/QDII
init_db()  # 测试里对全局 engine 建表，但请求走 override session（另一 engine）

# 分页相关
items.sort(...); items = items[:limit]         # 切片在排序之前——多页之间会错位、重叠
total = len(items_page)                        # total 当成页长度——前端分页器总页数算错
ach_map = {c: ... for c in codes_after_slice}  # 按切片后 codes 查 ach——DTO 内 rank_* 字段大量丢
```
### Correct
```python
q.filter(FundPerformance.dd_3y >= -abs(max_dd_3y))  # 绝对值语义
q.where(Fund.is_active == True, Fund.code.in_(resolve_universe_codes("bond")))
# conftest: create_engine("sqlite:///:memory:", poolclass=StaticPool)

# 分页相关
total = len(items)                          # total 在切片前算
ordered = valued_sort + empty_tail
items_page = ordered[offset : offset+limit]  # 切片在排序之后
return {"total": total, "items": items_page}
```

## 8. discovery-* tab「基金类型」粗类别映射契约（09-10-qdii-reits-coarse-mapping）

### 两层过滤模式

前端 UI 暴露**粗类别**（5 个：`股票型 / 混合型 / 指数型 / QDII / REITs`），用户勾选的也是粗类别；后端 SQL 只认**精确 subtype**（akshare 子类枚举，如 `QDII-普通股票`）。

```typescript
// apps/fund-select/src/lib/types.ts — 前端做粗→精展开
'QDII': ['QDII-普通股票', 'QDII-混合偏股', 'QDII-混合灵活', 'QDII-混合平衡', 'QDII-FOF', 'QDII-REITs'],
'REITs': ['Reits', 'REITs'],
// 展开后写入 ?market_type=QDII-普通股票,... 后端 IN (...) 过滤
```

后端 `_parse_market_types` 仅做 `split(',')`，不做粗→精展开（设计决策 D3：粗类别的语义归前端）。后端写单测时**必须模拟前端展开后的精确列表**，不要直接传 `["QDII"]` 给 `screen_discovery_stock(market_types=...)`——会得到空集（因为 `market_subtype` 字段值是 `QDII-普通股票` 等，没有 "QDII" 这个值）。

### 跨界 subtype 归类（QDII-REITs 边界 case）

`market_subtype` 字段值中部分 subtype 同时归属两个语义类别（如 `QDII-REITs` 既是 QDII 又是 REITs）。归类决策按**用户心智模型**而非纯语义——「QDII」粗类别包含所有 QDII 系列，与标的无关：

| 精确 subtype | SUBCLASS_TO_CATEGORY（后端） | COARSE_TO_SUBTYPES_STOCK 粗类别（前端） |
|---|---|---|
| `QDII-REITs` | `stock`（与 Reits/REITs 同组，避免落 `other`） | **`QDII`**（不是 `REITs`） |

**为什么 QDII-REITs 归 QDII 粗类别**：不勾「QDII」时用户期望"无任何 QDII 基金"，若归 REITs 则会出现名字带「(QDII)」的海外 REIT（鹏华美国房地产、嘉实全球房地产、诺安全球收益不动产等）——前端语义必须与用户直觉对齐。代价：勾 QDII 但不勾 REITs 时也能看到 QDII-REITs，但这与「QDII 大类」的语义一致。

### Common Mistake: 后端单测传粗类别而非精确 subtype

**Symptom**: `screen_discovery_stock(market_types=["QDII"])` 返回空集；测试失败。

**Cause**: 后端 `market_subtype` 字段没有值为 "QDII" 的记录，只有 `QDII-普通股票 / QDII-混合偏股 / ...` 等子串。粗→精展开由前端 `COARSE_TO_SUBTYPES_STOCK` 完成。

**Fix**: 单测里手写展开后的精确列表：
```python
qdii_subtypes = ['QDII-普通股票', 'QDII-混合偏股', 'QDII-混合灵活',
                 'QDII-混合平衡', 'QDII-FOF', 'QDII-REITs']
FilterService(db).screen_discovery_stock(market_types=qdii_subtypes)
```

### Tests Required（09-10 新增）

`tests/test_discovery_filter_service.py::TestScreenDiscoveryStock::test_qdii_reits_excluded_when_qdii_coarse_unchecked`：
- 断言 1：不勾 QDII（仅勾 REITs 展开 `["Reits", "REITs"]`）→ QDII-REITs 不命中
- 断言 2：勾 QDII（展开 6 个精确 subtype）→ QDII-REITs 命中
- 断言 3：勾 QDII + REITs → 两者都命中（QDII-REITs 只出现 1 次，靠精确列表去重）

### Gotcha: UI 5 粗类别 = universe 全集

`DISCOVERY_STOCK_SUBTYPES` 16 个 subtype 全部分配在 5 个粗类别里（无 "other"）。`DISCOVERY_BOND_SUBTYPES` 11 个分配在 4 个粗类别里（债基 universe 不含 REITs）。修改 `COARSE_TO_SUBTYPES_*` 时**必须保证 universe 全集仍被对应粗类别覆盖**——漏掉的 subtype 默认 `market_types=null` 走默认 universe 全集时会重新出现，与 UI 行为脱节。

## 8a. 前端粗类别 UI 一致性契约（09-11-bond-market-type-fix）

> 大白话：用户在筛选器看到的钮 = 用户在表格里看到的 chip = 实际能筛出来的基金。三者必须严格对齐，错一个就是用户被骗。债基 5 个钮里 REITs 钮点了等于没点（09-11 实战），就是这个契约破了。

### 三处必须对齐的真相源

| 真相源 | 类型 | 位置 |
|---|---|---|
| `*_MARKET_TYPE_OPTIONS` | UI 筛选器可选项（value + label） | `apps/fund-select/src/lib/types.ts:182-208` |
| `COARSE_TO_SUBTYPES_*` | 粗类别 value → 精确 subtype 列表（前端 → 后端 IN 过滤） | `apps/fund-select/src/lib/types.ts:214-228` |
| `SUBCLASS_TO_CATEGORY`（后端） | 精确 subtype → universe 成员判定（bond / stock / other） | `backend/fund-select/src/data/market_subtype_map.py` |

**三者一一对应**，任何一边改了必须三边同步，否则出现：钮能点 / 表格能看 / 筛选结果对不上的三角错位。

### Convention: 死选项三处同步清理

`COARSE_TO_SUBTYPES_*['某粗类别'] = []` 是**死选项征兆**——后端 universe 不含此粗类别任何 subtype，前端钮点了展开为空 array → `api.ts:33` 静默不传参 → 后端 `_parse_market_types(None)` → 走默认 universe 返回全部基金。

清理死选项必须**同时**删三处（不是一处）：
1. `*_MARKET_TYPE_OPTIONS` 删该粗类别选项
2. `COARSE_TO_SUBTYPES_*` 删该死键
3. `DISCOVERY_*_DEFAULT_FILTERS.market_types` 删该粗类别引用（否则 `FilterChipBar` 会渲染出无法从 `FilterPanel` 重新加入的死 chip）

09-11 实战：债基侧 REITs 死选项，先删 1 + 2 → 仍然在 3 留死引用 → commit 后自修（commit `dd08321` 包含 default filters 数组同步清理）。

### Convention: chip 文案 = OPTIONS label 唯一真相源

表格类型列 `<TypeCell>` 显示两层：上行 chip（粗类别）+ 下行小字（精确 subtype）。chip 文案**必须**从 `*_MARKET_TYPE_OPTIONS` 的 `label` 字段 derive，禁止硬编码第二份文案。

实现位置：`apps/fund-select/src/lib/types.ts` 导出 `STOCK_OPTION_LABELS` / `BOND_OPTION_LABELS`，由 `buildOptionLabelMap(*_MARKET_TYPE_OPTIONS)` 生成。

```typescript
// Wrong — 硬编码两份文案，第二份必漂
export const SUBTYPE_TO_LABEL: Record<string, string> = {
  '混合型-偏债': '混合债基',
  '指数型-固收': '指数债',
  // ... 改 OPTIONS 时忘改这里 → 用户看到 chip「混合型」, 筛选器显示「混合债基」
};

// Correct — 唯一真相源
function buildOptionLabelMap(opts: { value: string; label: string }[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const o of opts) out[o.value] = o.label;
  return out;
}
export const BOND_OPTION_LABELS = buildOptionLabelMap(BOND_MARKET_TYPE_OPTIONS);
```

### Convention: 跨 tab 渲染 FundTable 必须显式传 `marketKind`

`resolveCoarseLabel(subtype, kind?)` 是粗类别 → label 的解析器，`kind` 决定走 stock 还是 bond 的 label map：

- `kind === undefined` → 走 `STOCK ?? BOND` fallback（**仅**老 `/bond`、`/stock` tab 用，不区分 context）
- `kind === 'stock' | 'bond'` → 按指定 tab 解析 chip label

`FundTable.tsx` props 加 `marketKind?: 'stock' | 'bond'`（**optional，老 tab 不传**）。`discovery-bond/page.tsx` 传 `marketKind="bond"`，`discovery-stock/page.tsx` 传 `marketKind="stock"`。

不传 `marketKind` 的代码路径（老 `/bond`、`/stock` tab）**逐字节保持原行为**——不允许"为了统一让老 tab 也传"。

### Common Mistake: 改 OPTIONS 文案不查仓库里所有引用

**Symptom**: 改了 `BOND_MARKET_TYPE_OPTIONS` 里某项 label，单元测试过、生产跑通，但上线后用户报告"表格 chip 文案和筛选器对不上"。

**Cause**: 仓库里**至少 4 处**可能引用到 label 或粗类别名（按命中优先级排查）：
1. `DISCOVERY_*_DEFAULT_FILTERS.market_types`（数组元素是 OPTIONS 的 value）
2. `discovery-{bond,stock}/page.tsx` 顶部注释（文档漂移主灾区）
3. `api/routes.py` docstring（必须跟 `DISCOVERY_*_SUBTYPES` 长度同步；09-11 已把「10 个债券相关子类」改为「11 个」）
4. `tests/test_discovery_filter_service.py` 断言字符串

**Prevention**:
- 改 `*_MARKET_TYPE_OPTIONS` / `COARSE_TO_SUBTYPES_*` 后，**必须** grep `apps/fund-select` 与 `backend/fund-select` 全部相关引用（不止上面 4 处）
- 优先靠「唯一真相源」设计消除漂移（OPTIONS label derive），而不是靠"搜得全"

### Gotcha: 跨界 subtype 同时归属两个粗类别时归类决策按用户心智模型

见 §8「跨界 subtype 归类（QDII-REITs 边界 case）」。09-10 决策：QDII-REITs 归 QDII 粗类别（不勾 QDII 时不出现），代价是勾 QDII 但不勾 REITs 仍能看到 QDII-REITs。

**新增陷阱**：跨界 subtype 在 chip 展示时也要按归类决策走，不能按 `market_subtype` 字符串前缀匹配。`SUBTYPE_TO_COARSE_*` 反向 map 的值必须与 §8 表格里的归类决策**逐字一致**。

### Tests Required（09-11 新增）

`apps/fund-select` 无单测框架（仅 backend pytest）。契约靠 `pnpm build` + `next dev` 手动验证，09-11 实证：

- 改完 `BOND_MARKET_TYPE_OPTIONS` 删 REITs → `pnpm build` 通过 + 手动 `discovery-bond` 页面确认筛选器只 4 选项
- chip 文案与筛选器 label 逐字一致 → 手动 `discovery-bond` 表格确认 `混合型-偏债` 行 chip =「混合债基」
- 老 `/bond`、`/stock` tab 渲染逐字节不变 → 手动切换老 tab 确认（**重点**：老 tab 不传 `marketKind`，走 STOCK ?? BOND fallback）
- `DISCOVERY_BOND_DEFAULT_FILTERS` 不含 REITs → `FilterChipBar` 不渲染死 chip

### Wrong vs Correct

#### Wrong
```typescript
// ❌ 死选项单边清理 — 只删 OPTIONS 不删 COARSE_TO_SUBTYPES
BOND_MARKET_TYPE_OPTIONS = [{ value: '纯债型', ... }, { value: '混合型', ... }];  // 删了 REITs
COARSE_TO_SUBTYPES_BOND = { ..., 'REITs': [] };  // 忘了删 — 仓库里留不可达死数组

// ❌ chip 文案硬编码第二份真相源
function resolveCoarseLabel(s: string) {
  if (s === '混合型-偏债') return '混合债基';  // 改 OPTIONS 时必漂
  return SUBTYPE_TO_COARSE_STOCK[s] ?? SUBTYPE_TO_COARSE_BOND[s];
}

// ❌ 老 /bond tab 传 marketKind='bond'
<FundTable items={items} marketKind="bond" />  // 老 tab 数据走老 path, marketKind='bond' 会让老股票基金 chip 显示债基 label
```

#### Correct
```typescript
// ✅ 死选项三处同步清理
BOND_MARKET_TYPE_OPTIONS = [{ value: '纯债型', ... }, { value: '混合型', ... }, { value: '指数型', ... }, { value: 'QDII', ... }];
COARSE_TO_SUBTYPES_BOND = { '纯债型': [...], '混合型': [...], '指数型': [...], 'QDII': [...] };  // 无 REITs 键
DISCOVERY_BOND_DEFAULT_FILTERS = { market_types: ['纯债型', '混合型', '指数型', 'QDII'], ... };  // 数组同步

// ✅ chip 文案 derive
export const BOND_OPTION_LABELS = buildOptionLabelMap(BOND_MARKET_TYPE_OPTIONS);
function resolveCoarseLabel(s: string, kind?: 'stock' | 'bond') {
  if (kind === undefined) return SUBTYPE_TO_COARSE_STOCK[s] ?? SUBTYPE_TO_COARSE_BOND[s] ?? null;
  const coarse = (kind === 'stock' ? SUBTYPE_TO_COARSE_STOCK : SUBTYPE_TO_COARSE_BOND)[s];
  return coarse ? (kind === 'stock' ? STOCK_OPTION_LABELS : BOND_OPTION_LABELS)[coarse] : null;
}

// ✅ 老 tab 不传 marketKind，老 path 走 STOCK ?? BOND fallback
<FundTable items={items} />  // 老 /bond、/stock 用
<FundTable items={items} marketKind="bond" />  // discovery-bond 用
<FundTable items={items} marketKind="stock" />  // discovery-stock 用
```

## 9. SUBCLASS_TO_CATEGORY 完整枚举契约（09-10-subtype-coverage-fix）

`SUBCLASS_TO_CATEGORY` 是 akshare 27+ 个精确 subtype → 4 类 universe（stock / bond / other / 未声明）的**显式白名单**。**未知 subtype 降级 "other"**（不出现在 universe 中）——这是有意为之，让运维在数据新增/异常时显式补映射，避免静默错归。

### 当前完整映射（stock universe 16 个 / bond universe 11 个）

| universe | 精确 subtype 列表 |
|---|---|
| **stock** | 股票型 / 指数型-海外股票 / 指数型-其他 / 指数型-股票 / 混合型-平衡 / 混合型-绝对收益 / 混合型-灵活 / 混合型-偏股 / QDII-普通股票 / QDII-混合偏股 / QDII-混合灵活 / QDII-混合平衡 / QDII-FOF / QDII-REITs / Reits / REITs |
| **bond** | 债券型-中短债 / 债券型-混合一级 / 债券型-混合二级 / 债券型-混合债 / 债券型-利率债 / 债券型-信用债 / 债券型-长期纯债 / 指数型-固收 / QDII-纯债 / QDII-混合债 / 混合型-偏债 |
| **other**（不进 universe） | FOF-稳健型 / FOF-均衡型 / FOF-进取型 / 货币型-普通货币 / 货币型-浮动净值 / QDII-商品 / 商品 / 其他 |

### Convention: 修改 SUBCLASS_TO_CATEGORY 必须同步改前端 COARSE_TO_SUBTYPES_STOCK/BOND

`SUBCLASS_TO_CATEGORY` 控制"是否进 universe"；`COARSE_TO_SUBTYPES_STOCK` / `COARSE_TO_SUBTYPES_BOND` 控制"在 UI 上被哪个粗类别命中"。两者一一对应：

- 加 subtype 进 `SUBCLASS_TO_CATEGORY` 时，**必须**同时加进对应粗类别数组，否则用户勾不到
- 删 subtype 时同理两端都删，避免前端展开列表包含 universe 外的值（`market_types=[...]` 命中空集但用户不知道为啥）

### Convention: 跨界 subtype 必须显式归 stock 或 bond，不允许 "other"

09-10 实战踩坑：修复前 `指数型-股票` (5677 只) / `混合型-偏股` (5726 只) / `混合型-偏债` (1464 只) 漏在 SUBCLASS_TO_CATEGORY 之外，默认归 other，**前端 UI 完全搜不到**。这三类是 A 股 ETF/指数增强主流、偏股混合主流、偏债混合主流，规模巨大。

判定原则：
- `指数型-股票`：A 股 ETF / 指数增强（华夏沪深 300ETF 联接A 等）→ 投资标的是股 → **stock**
- `混合型-偏股`：偏股混合基金（股票仓位 ≥60%）→ **stock**
- `混合型-偏债`：偏债混合基金（股票仓位 ≤40%）→ **bond**

### 暂时保持 other 的 subtype

- `QDII-商品` / `商品`（黄金、原油等大宗商品基金）：不属于股基/债基范畴，避免污染 universe。等有需要再加第 6 粗类别「商品型」。

### Tests Required（09-10 新增）

`tests/test_discovery_filter_service.py`：
- `TestScreenDiscoveryStock::test_index_stock_included_when_index_coarse_selected` — 勾「指数型」粗类别展开（含 `指数型-股票`）→ 命中 `指数型-股票 / 指数型-海外股票 / 指数型-其他` 三种
- `TestScreenDiscoveryStock::test_partial_stock_included_when_mixed_coarse_selected` — 勾「混合型」（股基侧，含 `混合型-偏股`）→ 命中 `混合型-偏股`，**不**含 `混合型-偏债`
- `TestScreenDiscoveryStock::test_qdii_commodity_still_excluded_from_stock_universe` — `QDII-商品 / 商品` 默认不进 stock universe
- `TestScreenDiscoveryBond::test_partial_bond_included_when_mixed_coarse_selected` — 勾「混合型」（债基侧，含 `混合型-偏债`）→ 命中 `混合型-偏债 + 债券型-混合债`

### Gotcha: 修改 SUBCLASS_TO_CATEGORY 后 universe 规模会变

修复后 universe 实际规模（活跃基金）：
- stock: ~11.6k → ~17.3k（+5677 指数型-股票 +5726 混合型-偏股 - 重复？→ 单算）
- bond: ~7.3k → ~8.8k（+1464 混合型-偏债）

走默认 universe 的接口（`screen_discovery_stock/bond`、`universe_stats`、全量 refresh `universe_filter`）行为都会变化。前端首屏 P95 可能受影响（5 粗类别默认全选时结果集变大），本次不优化，留后续观察。

## 10. 全量 refresh pipeline profile 契约（09-11-bond-full-pipeline-trim）

### 两套独立的 refresh pipeline（不要混淆）

fund-select 实际有 **两套独立**的全量 refresh pipeline，不是同一套接不同 universe：

| 维度 | 市场 tab 全量（`market_full_pipeline`） | 债基/股基三分法（`scheduler.tasks`） |
|---|---|---|
| 入口函数 | `refresh_market_full_sync` | `refresh_configured_funds_sync` / `refresh_stock_funds_sync` |
| Universe 来源 | `ak.fund_name_em()` 全市场 ~2.8 万只 | `config/funds.yaml` / `funds_stock.yaml` 手工名单 |
| 循环模式 | 阶段化流水线 + 分阶段重算 codes | `for code: snapshot_fund(code)` 单只 IO |
| 主要写表 | `market_fund_rank` / `market_nav` / `fund_risk_metrics` / `fund_achievement_rank` | `funds` / `FundFees` / `FundHoldingsBond` / `FundPerformance` |
| 触发方式 | 手动（`/full/refresh` 端点） | daily scheduler + 手动 |
| 适用页面 | `/funds/discovery-bond` / `/funds/discovery-stock` | `/funds/bond` / `/funds/stock` |

**两者之间没有共享 universe、没有共享 fetcher、没有共享进度回调**。老债基三分法不跑 L4/L5（`snapshot_fund` 默认 `fetch_ranking=False`，`refresh_configured_funds_sync` 不调 `benchmark_refresh.refresh`）—— 本任务的"精简"只对市场 tab pipeline 有效。

### pipeline_profile 参数（市场 tab pipeline 内部切换）

`refresh_market_full_sync` 新增 `pipeline_profile: str = "stock"` 参数：

- `"stock"`（默认）：6 阶段全跑 — L0 universe → L1 rank → L2 size → L3 nav → L4 risk → L5 achievement
- `"bond"`：4 阶段，跳 L4 + L5 — 保留 L0/L1/L2/L3

非法值在函数顶部抛 `ValueError`，不写 `RefreshRun`。

### 债基详情页不消费的数据（L4/L5 跳过理由）

- **`fund_risk_metrics`** 6 指标（sharpe / ir / alpha / gamma / alpha_ir / excess_3y）：只有 `RowDetailDrawer.tsx`（股基详情页）import `RiskMetricsGrid`，`RowDetailDrawerBond.tsx` 完全没 import → 债基详情页不展示这 6 个指标
- **`fund_achievement_rank`** 同类排名：只有 `RowDetailDrawer.tsx` 消费 `detail.achievement_ranks`，债基详情页 / 列表页 / 筛选器均不消费

保留 L3 nav 是因为 `max_dd_3y` 是债基筛选维度（`discovery-bond/page.tsx:77`），且 nav 数据是 1y/3y 涨幅计算基础。

### main_run.total 按 profile 动态算

- stock: `len(codes) * 6`
- bond: `len(codes) * 4`

`RefreshRun.total` 在两处写入：初始化时（line 192，原"占位"）和 L2 后（line 273）。两处都用 `stages_per_code` 动态算。前端 `discoveryBondApi.getFullRefreshStatus` 拿到的 total/completed 比例与实际跑的阶段数匹配。

### 路由层接入

- `routes.py:444 discovery_bond_full_refresh` 显式传 `pipeline_profile="bond"`
- `routes.py:505 discovery_stock_full_refresh` 不传 profile → 默认 `"stock"`，行为不变
- `scheduler/tasks.py` 若有调用 `refresh_market_full_sync` 的入口需手动加 profile 参数（`pipeline_profile` 默认 `"stock"` 保证向后兼容）

### Tests Required（09-11 新增）

`tests/test_market_full_pipeline.py::TestPipelineProfile` 覆盖：

- `test_bond_profile_skips_l4_and_l5` — profile="bond" 时 L4/L5 sentinel 函数被设但 flag 仍为 False；`stage_results.keys()` 只含 L0/L1/L2/L3
- `test_default_profile_runs_all_six_stages` — 不传 profile → 6 阶段全跑（回归保护）
- `test_invalid_profile_raises_value_error` — `pipeline_profile="etf"` 抛 `ValueError` 且不写 `RefreshRun`
- `test_main_run_total_reflects_stages_per_code` — bond profile total = universe × 4；stock profile total = universe × 6

### Common Mistake: 把"债基市场刷新"当成"债基三分法刷新"

两者是独立 pipeline：
- 想精简债基市场刷新 → 改 `refresh_market_full_sync` + `discovery_bond_full_refresh`（本次范围）
- 想精简债基三分法 → 改 `refresh_configured_funds_sync`（独立任务，且老路径无 L4/L5 可精简）

### Gotcha: pipeline 跳过阶段后 `stage_results` 不造假

`stage_results` dict 在 profile="bond" 时**不写** `L4_risk` / `L5_achievement` key（不写占位如 `{"skipped": "..."}`）。前端轮询拿到的 `RefreshRun.total/completed/failed` 自然反映 4 阶段进度。日志里通过 `logger.info("跳过 L4/L5 阶段")` 留痕。

### 后续：合并两套 pipeline（不在本任务范围）

把"市场 tab 全量"和"债基三分法"合并成一个 profile-driven 的统一刷新系统，是更大的架构重构（涉及 universe 来源 IO、单只 vs 阶段化循环、字段映射、schema 差异）。本次不动。

## 11. 市场 tab 全量刷新预筛前端默认值（09-11-bond-full-refresh-default-10pct）

后端 `/discovery-bond/full/refresh` 与 `/discovery-stock/full/refresh` 的 `min_ret_3y` 都是 `Optional[float]`，**默认值只在客户端**。债基与股基收益弹性不同，禁止共用同一个 `min_ret_3y` 默认。

| 常量 | 位置 | `min_ret_3y` | 使用方 |
|---|---|---|---|
| `DEFAULT_FULL_REFRESH_FILTERS_BOND` | `apps/fund-select/src/lib/types.ts` | **10** | `discovery-bond/page.tsx` → `preFilters` → `FullRefreshDialog initial` |
| `DEFAULT_FULL_REFRESH_FILTERS_STOCK` | 同上 | **20** | `discovery-stock/page.tsx` 同上 |
| `DEFAULT_FULL_REFRESH_FILTERS` | 同上，**deprecated alias → STOCK** | 20 | 仅 `FullRefreshDialog` 在 `initial` 缺字段时的 fallback |

**Convention**: 债基页必须 import `_BOND`，股基页必须 import `_STOCK`。不要让债基走 deprecated alias，否则对话框默认会显示 20%。

**Gotcha**: `FullRefreshDialog` 用 `initial?.min_ret_3y ?? DEFAULT_FULL_REFRESH_FILTERS.min_ret_3y`。`??` 在 `null`/`undefined` 时落到股基 20%。债基 happy path 始终传入 `preFilters.min_ret_3y=10`，A1 不受影响；若日后 `initial` 漏传或把该字段清成 `null`，债基弹窗会回显 20%。

### Wrong vs Correct

```typescript
// Wrong — 债基页复用股基默认，对话框会显示 20%
import { DEFAULT_FULL_REFRESH_FILTERS } from '@/lib/types';
useState<FullRefreshFilters>(DEFAULT_FULL_REFRESH_FILTERS);

// Correct
import { DEFAULT_FULL_REFRESH_FILTERS_BOND } from '@/lib/types';
useState<FullRefreshFilters>(DEFAULT_FULL_REFRESH_FILTERS_BOND);
```

## 12. market_full_pipeline profile + L6_fees_holdings（09-11-bond-detail-fees-holdings-writeback）

`refresh_market_full_sync` 加 `pipeline_profile: str = "stock"` 参数控制阶段序列。债基详情页自给自足（不再依赖老 v1 yaml 写 `FundFees` / `FundHoldingsBond`）。

| profile | 阶段序列 | `main_run.total` |
|---|---|---|
| `"stock"`（默认） | L0 universe → L1 rank → L2 size → L3 nav → L4 risk → L5 achievement | `codes × 6` |
| `"bond"` | L0 universe → L1 rank → L2 size → L3 nav → **L6 fees_holdings** | `codes × 5`（跳过 L4/L5） |

**路由层契约**：
- `discovery_bond_full_refresh`（`routes.py:470`）显式 `pipeline_profile="bond"`
- `discovery_stock_full_refresh` 不传参（默认 `"stock"`，6 阶段行为不变）
- `refresh_configured_funds_sync`（v1 yaml 老路径）独立运行，不进本 pipeline

**L6_fees_holdings 契约**（仅 profile="bond"）：
- 防御性二次过滤 `codes ∩ market_subtype ∈ DISCOVERY_BOND_SUBTYPES`
- `ThreadPoolExecutor(max_workers=5)` 对齐 `market_nav_fetcher.MAX_WORKERS`
- **复用**：`fetch_fees` / `fetch_bond_hold` / `analyze_holdings` / `persist_snapshot`
- **不复用** `snapshot_fund`：避免重复拉 basic/nav/performance（L0-L3 已写过 `funds` / `market_nav`）
- `holdings_year = str(date.today().year - 1)` 对齐老路径默认（上年年报）
- 单只失败仅入账 `errors`，**不重试**（激进跳过，避免长尾）
- 每只立即 `db.commit()`（断点续传）

**Validation & Error Matrix**：
| 输入 | 行为 |
|---|---|
| `pipeline_profile = "stock"` | 6 阶段，不调 `fetch_fees` / `fetch_bond_hold` |
| `pipeline_profile = "bond"` | 5 阶段，跳 L4/L5，调 L6 |
| `pipeline_profile` 未传 | 默认 `"stock"`（向后兼容） |
| `pipeline_profile = "invalid"` | `ValueError`（函数顶部校验） |
| `universe_filter` 不在债基 | L6 跑空，`bond_codes = []`，不报错 |
| 单只 `fetch_fees` 抛异常 | 外层 try/except 捕获 → `failed += 1`，其余继续 |
| 单只 `fetch_bond_hold` 返回 `[]` | `out["holdings"] = None` → `persist_snapshot` 跳过写入 |

**Convention**：
- profile 默认值 `"stock"` 必须保留——所有"不显式传参"的调用点（含 scheduler）行为不变
- 复用 `persist_snapshot` 时只填 `snap["fees"]` / `snap["holdings"]`，**不要**重复填 `basic` / `performance`（已写）
- L6 阶段命名 `_stage_l6_fees_holdings`，**不要** 改名 `_stage_l4_fees`（避免与股基 L4 视觉混淆）
- lazy import `fetch_fees` / `fetch_bond_hold` / `persist_snapshot`（防循环依赖 `refresh_service` → `market_full_pipeline` → `refresh_service`）

**Gotcha**：
- `fetch_bond_hold` 内部已吞异常返 `[]`，但 `fetch_fees` 失败会**抛异常**（不吞）。L6 内层不要包 try/except 吞 `fetch_fees`，否则外层 `failed += 1` 永远不触发（09-11 L6 self-fix 教训）
- `persist_snapshot` 用 `snap.get("fees")` truthy 判断——空 dict `{}` 也会跳过写入。`_fetch_one_fees_holdings` 用 `fees if fees else {}` 是正确选择，避免空 dict 触发无意义 upsert
- 前端 0 改动：详情页 `fundApi.getDetail` 接口和 DTO 不变，本任务纯后端写表

**测试覆盖**（`tests/test_market_full_pipeline.py`，24 条全过）：
- `TestPipelineProfile`（4 条）：bond=5 阶段、stock=6 阶段、非法值 ValueError、main_run.total 公式
- `TestL6FeesHoldings`（5 条）：调用次数 = 债基 codes、defensive 过滤、单只失败容错、persist_snapshot 触发条件（空 dict 跳过）、stock profile 不调 L6

**Wrong vs Correct**

```python
# Wrong — 路由层漏传 profile，bond 默认走 6 阶段，债基又被写废 66 分钟
background.add_task(refresh_market_full_sync,
                   universe_filter=list(DISCOVERY_BOND_SUBTYPES),
                   min_ret_3y=min_ret_3y, ...)

# Correct
background.add_task(refresh_market_full_sync,
                   universe_filter=list(DISCOVERY_BOND_SUBTYPES),
                   pipeline_profile="bond",   # 显式声明
                   min_ret_3y=min_ret_3y, ...)
```

```python
# Wrong — L6 内层包 try/except 吞 fetch_fees 异常
def _fetch_one(...):
    try:
        out["fees"] = fetch_fees(code)
    except Exception:
        out["fees"] = {}  # 吞异常 → 外层 failed += 1 永不触发

# Correct — 让异常冒泡到外层 _stage_l6 捕获
def _fetch_one(...):
    out["fees"] = fetch_fees(code)   # 异常自然传播
    ...
```

## 13. 夏普榜单：每周入选记录与周榜发布（11-04-fund-sharpe-weekly-board，2026-11-05）

### 1. Scope / Trigger

- 新增独立「夏普榜单」：两个股基周任务采集后原子发布带规则版本的周榜（批次 + 观测两表），只读 API 聚合，前端独立页（前端契约见 [frontend/fund-sharpe-board.md](../../../frontend/fund-sharpe-board.md)）。
- 触发本节的条件：改周榜表/发布判定/采集冻结（capture）/聚合排序分页/`/sharpe-board` API 任何一处。

### 2. Signatures

**新表（create_all 幂等建表，不改旧表）**

- `sharpe_board_weeks`：id PK；`(source, profile_version, week_start)` 联合唯一；profile_json（完整规则副本）/profile_hash/algorithm_version；`status ∈ complete|failed|skipped_no_new_data`（running 复用 scheduler 内存态，不落表）；run_id/trigger/started_at(not null)/finished_at/published_at；selected_count/errors_json/diagnostics_json。时间列存 UTC 挂钟 naive，展示层转北京时间。
- `sharpe_board_observations`：id PK；`(week_id, code)` 联合唯一；week_id FK 但**不引用实时 Fund 表级联**（清盘/改名/失活不抹历史）；name 是入选时名称快照；sharpe 只存有限数；metric_calculated_at/returns_end_date/sample_days/evidence_json。

**核心函数**（`src/services/sharpe_board_service.py` / `src/services/sharpe_capture.py`）

```python
recording_week(started_at) -> date          # aware datetime → 北京时间所在周周一；naive 抛 ValueError
get_profile(source, version) -> dict        # 深拷贝；未知组合 KeyError（API 层转 404）
canonical_json / canonical_hash(payload)    # sort_keys+紧凑分隔符+ensure_ascii=False / sha256
publish_week_board(db, capture, *, source, profile_version, week_start, trigger, ...)
    -> tuple[SharpeBoardWeek, bool]         # (周行, 是否本次写入)；单事务写批次+全部观测
```

**采集冻结**：`SharpeRunCapture(run_id, base_rows, risk_rows, errors, diagnostics, universe_codes, filters, collection_prefilters)`；接线点 = `weekly_refresh.py` 仅 stock/discovery-stock 两条（bond 不接、普通页面刷新不接）。链路函数（`refresh_stock_funds_sync` / `refresh_market_full_sync` / `market_risk_refresh.refresh` / `refresh_fund_risks`）加可选 `capture=None`，**旧路径逐字节零行为变更**。

### 3. Contracts

- **规则 profile**：`(stock, v1)`（雪球 yaml 名单，market_subtypes=None）与 `(discovery-stock, v1)`（market_subtypes=DISCOVERY_STOCK_SUBTYPES 确定副本 + 采集预筛 min_ret_3y=20/min_size_yi=5/min_mgr_exp=5）。filters=入选条件（成立≥3年/规模≥5亿/回撤绝对值≤30%/经理≥5年/夏普≥0.8/不排 QDII）。**记录参数 filters.min_sharpe 与展示参数 min_latest_sharpe 分开**。规则变更必须换 version，不改旧周行。
- **周键**：任务 `started_at`（非 finished_at）转 Asia/Shanghai 所在周周一；跨周完成仍归开始周。
- **冻结范围（易漏）**：入选谓词消费的 `dd_3y` 在 `FundPerformance` 行上，`freeze_base_row` 冻结不到——两条链路必须在 commit 点调 `freeze_dd_rows` 合并进 `base_rows[code]["dd_3y"]`，发布侧只读 capture，**禁止回读共享最新表**（普通刷新会覆盖）。risk_rows 冻结本轮 sharpe + `returns_end_date` + `benchmark_source` + `calculated_at`。
- **API**：`GET /api/funds/sharpe-board`，参数 `source=stock|discovery-stock`（默认 discovery-stock）/`profile_version=v1`（未知 404）/`min_latest_sharpe` 可空 [-10,10]/`min_weeks>=1` 默认 1/`latest_only` 默认 false/`range=3m|6m|1y|all` 默认 all/`page>=1`/`limit 1..200` 默认 50。返回 9 字段：profile/latest_published_week/latest_attempt/stale/total/items/weeks/series/diagnostics——**全部在 Pydantic DTO 显式声明**（§3a 静默砍字段）。items=当页（code/name/listed_weeks/consecutive_weeks/latest_sharpe/last_listed_week/on_latest_board）；series=全部命中不随分页。静态 router 必须注册在通用 `/{code}` 详情路由**之前**（main.py）。
- **聚合顺序**：complete 周全历史聚合 → 展示筛选（min_latest_sharpe 含等号、min_weeks、latest_only 用当前来源最新 complete 周而非各基金最后记录周）→ 排序 `(listed_weeks DESC, latest_sharpe DESC, code ASC)` → total 切片前算 → 切片（§分页不变量）。weeks 周历=首次观测周→当前周周一，range **只裁起点且起点对齐回周一网格**，终点恒为当前周；失败/停机/空榜周留位。consecutive_weeks=从最近上榜周向前数相邻自然周，缺席/未知中断（**§21 起细化：数据缺口周不中断，真实缺席才中断**）。stale=当前周无 complete 榜。

### 4. Validation & Error Matrix

| 条件 | 行为 |
|---|---|
| capture.errors 非空（nav 失败/阶段失败/基准风险错误/collector 崩溃） | 不发榜，记 failed（returned failed==0 也会漏报，errors 是唯一证据） |
| universe 去重后为空 | failed（不发空榜冒充零入选） |
| 有效全量输入零入选 | complete 空榜（selected_count=0，有效空状态） |
| sharpe NULL/NaN/Infinity 或无本轮证据 | 不写观测，计 diagnostics；nav 失败 code **完全不进 risk_rows** |
| 样本尾日相对上次发布全部无更新 | skipped_no_new_data（首次发布无「上次」直接发布） |
| 同周已有 complete | 冻结返回 (已有行, False)；failed/skipped 可同周成功重试；并发 IntegrityError 重读返回已有 complete |
| 发布抛错 | 单事务 rollback 零残留；snapshot_status=failed，不抹 collector 结果、不阻断队列 |
| API 非法参数 / 未知版本 | 422 / 404 |

### 5. Good/Base/Bad Cases

- Good: A=[0.95,缺席,1.05]、B=[0.90,0.92,0.94] → B(3周) 排 A(2周) 前；A values `[0.95,null,1.05]` 断线。
- Base: 首次上线零历史 → 首次成功发布后开始积累，如实显示 0/1 周。
- Bad: 用 finished_at 归档周、发布时回读被普通刷新覆盖的最新行、把 capture.errors 非空当零入选发 complete 空榜。

### 6. Tests Required

- `test_sharpe_board_service.py`：唯一约束/跨年周键/三状态区分/complete 冻结/tmp_path 重开保留。
- `test_sharpe_board_capture.py`：**nav 失败不冒充旧值**（errors 有证据 + risk_rows 无该 code）、覆盖写隔离（带反证断言）、谓词与 SQL 等价（等号/负回撤/NULL/QDII/精确 subtype）。
- `test_sharpe_board_service.py`（发布）+ `test_weekly_refresh.py`：202 只全量去重、中途失败 rollback 零残留、bond/普通刷新不发布、周键用 started_at。
- `test_sharpe_board_api.py`：implement.md 固定断言（total==1/items[0]==000001/series values）、三键排序、`range=1y` **周历终点==当前周且全周一网格**（2026-11-05 实锤 365 天裁剪落周日导致全 null 的回归）。

### 7. Wrong vs Correct

```python
# Wrong — 365=52周+1 天，raw cutoff 落周日，周历整体脱离周一观测键 → values 全 null
start = current - timedelta(days=cutoff_days)
# Correct — 裁剪起点对齐回周一，终点保持当前周
start = current - timedelta(days=cutoff_days)
start -= timedelta(days=start.weekday())
```

```python
# Wrong — 发布时回读实时表（可能已被普通刷新覆盖）
perf = db.get(FundPerformance, code).dd_3y
# Correct — 只读 capture 冻结快照（含 freeze_dd_rows 合并的 dd_3y）
pred_input = capture.base_rows[code] | {"sharpe": capture.risk_rows[code]["sharpe"]}
```

---

## 14. 经理维度：采集刷新契约（11-11-fund-manager-tab-refresh）

### 14.1 端点是 `/managers/refresh`，注册顺序在 `/{manager_id}` 之前

`GET /api/funds/managers/refresh` 与 `/managers/refresh/status` 必须注册在
`/managers/{manager_id}` **之前**。FastAPI 按注册顺序匹配，反了会把 `refresh`
当作经理 ID 走详情查询（404「经理不存在: refresh」）。
`test_refresh_route_not_swallowed_by_detail_route` 同时断言存在性与顺序。

```python
# Correct —— 静态段在前
@router_managers.get("/refresh")           ...
@router_managers.get("/refresh/status")    ...
@router_managers.get("/{manager_id}")      ...
```

### 14.2 `force` 是刷新语义的分水岭

`manager_refresh.refresh(force=False)` 默认保持断点续采（只采 `fetched_at IS NULL`）。
API 入口固定传 `force=True`：经理档案没有增量口径（东财不提供变更时间），
「刷新」的唯一正确含义是全量覆盖。

```python
# Wrong —— 只接入口不改采集，第二次点刷新空转（pending_ids 恒为空）
background.add_task(refresh_managers, db)
# Correct
refresh_managers(db, task_id=task_id, force=True)
```

幂等靠 `_replace_tenures`（按 `manager_id` 先 delete 再 insert），不是 upsert。

### 14.3 `RefreshRun` 三字段按「人」计

| 字段 | 契约 |
|---|---|
| `total` | 本轮 `pending_ids` 人数（M1 算完 scope 才有值；之前为 0） |
| `completed` | 每人递增内存值，每 5 人落库（`PROGRESS_COMMIT_EVERY`） |
| `failed` | 同上 |

页面进度条用 `(completed + failed) / total`。因为 `total` 在 M1 之后才确定，
刷新端点先 commit 一个空 `RefreshRun` 拿到 `task_id`，采集线程再回填。

### 14.4 `RefreshRun.errors` 必须是 JSON 数组字符串

`/refresh/status` 契约是 `errors: list[str]`，实现走 `json.loads(run.errors)`。
写入方必须 `json.dumps(list)`：

```python
# Wrong —— 换行拼接，前端 json.loads 抛错后 errors 恒为空
run.errors = "\n".join(stats["errors"])
# Correct
run.errors = json.dumps(stats["errors"][:20], ensure_ascii=False)[:1900]
```

读取方对非 JSON 旧行降级为 `[raw]`，不能 500。

### 14.5 长任务必须单飞

全量采集 1881 人 × 0.3s ≈ 40 分钟。`threading.Lock` 非阻塞 `acquire` 失败 → 409，
不重复起线程：两个线程同时 `_replace_tenures` 同一批经理会撞
`uq_tenure_mfc` 唯一键。

后台体自己开 `SessionLocal()`（`BackgroundTasks` 与 `get_db` 依赖生命周期不同），
`finally` 里关 session 并**释放锁**——漏释放会让后续刷新永久 409。

### 14.6 前端长任务轮询节奏

`RefreshStatusPopover` 对 managers 用 10s 轮询（`POLL_INTERVAL_SLOW_MS`）。
1s 轮询跑 40 分钟会打出约 2400 次请求。判断依据是 `refreshUrl.includes('/managers/')`。

### 14.7 经理 tab 必须复用共享表现层

`managers/page.tsx` 曾自建 header + 内联筛选行 + 文字箭头排序，与其余 5 tab 视觉漂移。
契约：**任何 tab 都不得自写 header**——`FundsHeader` 是唯一入口
（加 tab 就扩 `FundsTab` / `TITLE` / `REFRESH_URL`，必要时加 `totalUnit`）；
筛选面板用 `FilterPanelShell` + `DimensionControl`；排序用 `SortableHeader`。

### 14.8 排序白名单要覆盖所有可排序列

页面给了排序按钮，`VALID_SORTS` / `SORT_COLUMNS` / getter 三处必须同步，
否则该列点了会静默退回默认排序。「最长任期」列曾错绑 `managed_fund_count`
且 `longest_tenure_years` 不在白名单——排序结果按「管理过几只」排，语义错。

### 14.9 页面需 `Suspense` 包裹

`FundsHeader` 内部 `useSearchParams()`（`?scheduler=1` 自动开齿轮弹框），
静态预渲染要求页面在 Suspense 边界内，否则 `pnpm build` 报
`useSearchParams() should be wrapped in a suspense boundary`。

---

## 15. 经理派生指标：任期胜率 / 独管比例 / 代表作背离（11-12）

三个指标全部由 `manager_tenures` 聚合派生，**不新增采集**。

### 15.1 口径

| 指标 | 定义 | 备注 |
|---|---|---|
| `tenure_win_rate` | `tenure_return > 0` 的任期占比 % | 无回报数据的经理为 None；不设天数下限（与 annualize 的 90 天地板是两回事） |
| `solo_ratio` | is_current 任期中该基金仅一位（stock_active 范围内）经理的占比 % | 共管判断只需布尔，范围缩小不影响结果 |
| `rep_divergence` | `longest_tenure_annual − tenure_weighted_annual` pp | 仅展示不进筛选；>15 视为代表作依赖（幸存者偏差） |

### 15.2 SQLite 布尔求和陷阱

`func.sum(col > 0)` 编译成 `sum(tenure_return > 0)`，SQLite 执行正确，但
SQLAlchemy 把结果列类型标成 Boolean —— Python 侧拿到 `True/False` 而不是整数，
`True * 100 / 3` 会得出 33.3（把 3 段 2 胜算成 1 胜）。必须用
`func.sum(case((col > 0, 1), else_=0))` 显式转整数。

### 15.3 聚合在服务层、筛选在 Python 侧

派生指标不落库：`_load_aggregates` 两条 GROUP BY（1881 经理 / 2 万任期，
毫秒级）在 `screen()` 内存中合并进 DTO；`min_win_rate` / `min_solo_ratio`
筛选取「None 不命中」语义（与 SQL 侧 NULL 语义一致）。
排序白名单新增 `tenure_win_rate` / `solo_ratio`（`SORT_COLUMNS` 中列为 None，
仅用于取默认方向 desc）。

### 15.4 详情接口也要带聚合

`get_detail` 与 `screen` 共用 `_load_aggregates`，否则列表有值、详情 None。

---

## 15.5 历任基金行的近 1 年 / 近 3 年 / 近 5 年（与股票 tab 同口径）

经理明细页展开后的「历任基金」表在「年化」后加三列 `近1年` / `近3年` / `近5年`，
数据源与股票 tab 主表**完全一致**（同表、同回退链、同排名口径）：

| 字段 | 来源 | 备注 |
|---|---|---|
| `ret_1y` / `ret_3y` | `FundPerformance`（雪球链路）优先 → `MarketFundRank`（市场链路）回退 | 逐项回退：perf 的某列为 null 时取 market 值 |
| `ret_5y` | `FundPerformance` 唯一链路 | `market_fund_rank` 表**没有** `ret_5y` 列（市场链路只到近3年/今年以来/成立以来），故无回退，缺失即为空 |
| `rank_1y` / `rank_3y` / `rank_5y` | `FundAchievementRank`（`阶段业绩` / `近1年`、`近3年`、`近5年`） | 走 `src/utils/rank.py` 的 `parse_peer_rank`（与 filter_service 同一份实现） |

### 15.6 口径差异必须写在表头提示里

这几列是**基金自身时间窗口**的收益，与同一行的「任职回报」（按该经理任职窗口算）
**不是一回事**：经理离任后基金可能已换人。所以列名用「近1年」而非「任职近1年」，
表头加 tooltip 说明差异，避免读者把两者当同一口径。

### 15.7 排名解析下沉到 utils

`_parse_peer_rank` 原在 `filter_service` 私有。经理明细也要显示同类排名，
两处共用一份实现，故提取到 `src/utils/rank.py`；`filter_service._parse_peer_rank`
保留为薄封装（旧调用点与测试 import 路径不变）。

### 15.8 展开行的 colSpan 必须等于列表表列数

经理列表表有 **12** 列（经理/公司/从业/年化·含离任/在管年化/胜率/独管/最长任期/
回撤/夏普/规模/在管）。展开的详情行 `td` 必须写 `colSpan={12}`——写成 11 会
少合并「在管」列（5.5rem），详情面板比列表窄一截，肉眼看是两个不同宽度。
加载态与空态的 `colSpan` 同样要改。

### 15.9 详情内层表要 table-fixed + 显式列宽

展开层里的「历任基金」表若不设 `table-fixed` 且不显式给列宽，内容会把表格
撑出容器，父级 `overflow-x-auto` 出现横向滚动条，视觉上又和列表对不齐。
给每列显式 `w-[…]` 后，内层表与外层列表表同宽铺满。

**列宽总和要 ≤ 可用宽度**：外层 `td` 的内容宽 = 列表表宽 − 左右 padding
（1280 视口约 1044px）。列宽总和超出时 `table-fixed` 会按比例压缩，最窄的列
（代码列要塞「在榜 N 周」徽章）就被挤到内容溢出。

**flex 子项要 `shrink-0`**：`RankInline` 的排名色点是 `w-1.5` 的固定尺寸，
在窄列里会被 flex 压成 0 宽（色点消失）。给色点与百分比加 `shrink-0`。

### 15.10 详情表列宽与内容匹配

| 列 | 宽度 | 依据 |
|---|---|---|
| 代码 | 8rem | 6 位代码 + 「在榜 N 周」徽章（约 61px） |
| 名称 | 7rem | 基金名最长约 10 字，超出截断 |
| 任职期间 | 9.5rem | 「2021-02-11~2025-04-12」最长 21 字符 |
| 近1年/近3年/近5年 | 7rem | 收益值（如 `+110.95%`）+ 排名行（色点 + `18.9%` + `395/2091`） |

---

## 16. 经理 ↔ 基金跨 tab 关联（11-12 双向闭环）

### 16.1 URL 直达参数是唯一跨页交互协议

| 落点页 | 参数 | 行为 |
|---|---|---|
| 4 个基金 tab | `?code=` | 打开详情抽屉（stub 只传 code），用后 `history.replaceState` 清参数防刷新重弹 |
| 经理页 | `?keyword=` | 预填搜索框 |
| 夏普榜单 | `?focus=` | 聚焦该基金曲线；code 不在本次榜单时还原 null |

### 16.2 basePath 陷阱：Link href 不带 /funds 前缀

Next.js `Link` 自动补 `basePath=/funds`，href 写 `/funds/managers` 会产出
`/funds/funds/managers`（404）。跨页链接一律写相对路径（`/managers?...`）。
`<a href>` 原生标签才需要手写前缀（FundsHeader 的「返回首页」用的 `/`）。

### 16.3 详情抽屉 stub 模式

`RowDetailDrawer` / `RowDetailDrawerBond` 接受 `stub?: string | null`：
fund 为 null 但 stub 有 code 时复用同一抽屉壳，头部先显示 code、
`detail?.name || effective.name` 回填名称。**依赖数组必须用
`effective?.code`**——写 `fund?.code` 时 stub 模式不触发拉取（fund 恒 null），
抽屉空白。

### 16.4 详情接口路径（D2 决策）

`/api/funds/{code}` 是唯一详情端点；discovery-* 没有自己的 `/{code}`。
抽屉统一走 `fundApi.getDetail`（Bond drawer）或 `stockApi.getDetail`
（stock drawer，路径 `/api/funds/stock/{code}` 与 `/api/funds/{code}`
返回同构 DTO）。给 discovery 页接新跳转时不要发明新端点。

### 16.5 归属徽章数据（affiliation）

`get_detail` 的每条 tenure 带 `affiliation`：`tab`（老 yaml 名单优先于
market_type 全量）/ `board_weeks`（complete 周观测计数，历史累计）/
`fund_name_market`。列表行带 `board_on_current` / `current_fund_total`
汇总。并行会话重写同文件的 JSX 时必须核对 `AffiliationBadges` 调用点
是否还在（本次曾被 8a11b2a 覆盖回纯文本）。

---

## 17. 夏普走势页：现算滚动夏普（11-13-fund-sharpe-trend，2026-11-13）

### 17.1 Scope / Trigger

新增导航第七 Tab「夏普走势」（`/funds/sharpe-trend?code=xxx`），用现算的
周频滚动 3 年夏普曲线回答「这只基金稳不稳」。触发本节的条件：改
`/sharpe-trend` API、`sharpe_trend_service` 口径/KPI、走势页前端、三处入口。

**与夏普榜单（§13）的分工**（不要合并）：
- 榜单 = 每周冻结的周观测（只在 ≥0.8 入选时记录，**有幸存者偏差**），
  回答「谁一直好」，横向比 N 只。
- 走势 = 现算完整滚动曲线（**跌破 0.8 也看得见**），回答「这一只稳不稳」，
  纵向单只。
- 两者最新值同口径，可互相印证。

### 17.2 口径决定：纯净值，不 join 基准（**最关键**）

`risk_service.compute_risk_metrics` 在有基准时会把 `r_p` 与 `r_b` 做
inner join。生产库 `fund_benchmark` 只有 561 只、最早 2023-11-08，
**会把历史 3 年窗口截断成 1 年**。

实测（000628，同一份净值、同一窗口定义，仅差是否 join）：

| 窗口截止 | join 基准 | 纯净值 | 样本天数 |
|---|---|---|---|
| 2026-11-13 | 0.9753 | 0.9216 | 723 vs 728 |
| 2024-12-31 | 1.8048 | 0.3298 | 280 vs 729 |
| 2024-09-30 | 2.4216 | 0.6845 | 219 vs 729 |

若沿用 join 口径，曲线会在 2025 年前后出现**虚假断崖**（同一只基金被
算成 2.42「优秀」而非 0.68「不稳定」），恰好与「稳定性」判断相反。

**决定：走势页用纯净值口径** —— 只用 `R_p`（东财日增长率/100）与
`R_f`，不 join `fund_benchmark`。夏普定义本来就不需要基准，基准只服务
IR/alpha。`rolling_sharpe_series` 的签名里没有 `r_b`，且回归测试
`test_benchmark_rows_do_not_truncate_window` 逐点比对「有/无基准行」结果
一致 + 历史窗口 sample_days ≥700。

公式与 `risk_service` 一致：`mean(excess)/std(excess, ddof=1) × √252`；
`std=0`/NaN → 无定义（该周不出点）。`MIN_SAMPLE_DAYS=250`、
`TRADING_DAYS=252`、`WINDOW_YEARS=3`。

`risk_free_rate` 生产库当前为**空表**（fetcher 存在但未入调度）→
`rf_basis="zero"`，如实标注不静默；有数据时 `"rate"`。

**最新点与列表值的对齐**：列表夏普窗口用 `today - 3年`，走势最后一点
用「最新净值日所在周的最后交易日」回看 3 年。末日相同时数值一致
（000628 实测 0.9216 vs 走势 0.9163，差 <0.6% 来自窗口起点差 1 天 /
样本 728 vs 729），契约允许此小数级差异，不强行改算法。

### 17.3 API

`GET /api/funds/sharpe-trend/{code}?range=all|3y|1y`（默认 all）

- 静态路由必须在通用 `/{code}` 详情路由**之前**注册（`main.py`），
  否则 `/sharpe-trend/000628` 被吞掉报「基金不存在: sharpe-trend」。
- 三个 DTO 全部在 `models.py` 显式声明（§3a 静默砍字段）：
  `SharpeTrendPointDTO`（date / sharpe / sample_days）、
  `SharpeTrendStatsDTO`（11 字段）、`SharpeTrendResponse`（9 字段）。
  后端加字段要三处同步：`models.py` ↔ `lib/sharpe-trend.ts` ↔ 页面。
- `range` 只裁**返回的点集**，不改每个点的 3 年滚动窗口。
- 错误语义（与正常空态分开）：

| 场景 | 响应 |
|---|---|
| code 不在 Fund 表 | 404（**不打网络**：akshare 对未知代码抛解析异常，会被误判 502） |
| 净值网络失败 | 502 `净值拉取失败: ...`（可重试） |
| 净值 < 250 日 | 200 + `points=[]` + `diagnostics.insufficient_history`（正常空态） |
| 无有效点但样本够 | 200 + `diagnostics.no_valid_points` |

- `rf_basis` / `algorithm_version="trend-v1"` / `diagnostics` 必须如实返回，
  前端在 KPI 次级行展示口径。

### 17.4 KPI 定义（threshold 默认 0.8，与榜单入选线一致）

- 有效点 = sharpe 非 None 的点；None（样本不足/无定义）不计入统计，
  但**打断**连续达标/连续低于的计数。
- `current` = 最后一个有效点（不是最后一个点）；`max/min/mean` 基于区间内有效点。
- `above_ratio` = ≥阈值周数 / 有效周数（≥ 含等号）。
- `consecutive_above` = 从最新点往回连续 ≥阈值 的点数。
- `longest_below` = 全区最长连续 <阈值 的周数（回答「最差能差多久」）。
- `trend_12w` = 最近 12 个有效点的最小二乘斜率（每周变化量）；不足 12 → None。

### 17.5 性能与缓存（不落库）

实测：净值拉取 0.12s + 603 个周点计算 0.17s ≈ **0.3s/请求**，
无需预计算落库。`sharpe_trend_service._cached_nav` 是进程内 TTL 1h
缓存（按 code 键），失败不缓存（可重试）。**本页纯读：不写任何表、
不进调度、不影响周榜发布。**

### 17.6 前端契约

- `FundsNavigation` 七 Tab；走势页自行组装头部（同 sharpe-board 模式，
  不套 FundsHeader），`active="sharpe-trend"`。
- 无 code → 代码输入框引导态（不造曲线）；带 code → 自动加载。
- 图表**复用** `SharpeChart` + `buildSharpeChartOption`（单 series，
  `minLatestSharpe=0.8` 挂参考线），`dynamic(ssr:false)`。
- `lib/sharpe-trend.ts` 独立 DTO / URL parse / fetch（全路径
  `/funds/api/funds/...`）；code/range 切换用 AbortController 中止旧请求。
- basePath 铁律：所有跳转 Link 用相对路径 `/sharpe-trend?code=...`，
  **不得**带 `/funds` 前缀。

### 17.7 三处入口（**第一版只支持股基**）

| 入口 | 改动 | 注意 |
|---|---|---|
| 股基两 tab 列表代码列 | `FundTable` 加 `trendEnabled` prop，仅 `stock`/`discovery-stock` 传 true | Link 必须 `stopPropagation`，否则同时触发 `onRowClick` 开抽屉 |
| 详情抽屉夏普 KPI | `RiskMetricsGrid` 加 `trendHref` prop；`DetailHero` 传 `/sharpe-trend?code=${fund.code}` | 只有 `RowDetailDrawer`（股基）用；债基 `RowDetailDrawerBond` 不用；显式分支渲染 Link/div，别用动态 Wrapper（TS 会把 Link 的必填 href 强加给 div） |
| 夏普榜单行代码 | `SharpeBoardTable` 代码 → Link，下方保留极小「详情」按钮 | 行点击是聚焦，Link 需 `stopPropagation`；名称点击仍开抽屉 |

债基两 tab 不传 `trendEnabled`（默认 false）→ 代码纯文本，零行为变化。
后端对任意 code 都能算，但前端第一版不暴露债基入口。

### 17.8 Tests Required

- 后端 `tests/test_sharpe_trend.py`（33 用例）：纯净值口径不被基准截断
  （**最关键回归**）、rf 空表/有值、样本不足、缓存失败可重试、
  KPI 边界（全达标/全不达标/恰好 12 点/单点/None 缺口打断连续计数）、
  range 只裁点不改窗口、路由顺序、404/502/422/insufficient 200。
- 前端 `lib/sharpe-trend.test.ts`（13 用例）：URL parse 非法值回退、
  href 相对路径、格式化、状态分类、fetch 查询串与错误处理。
- 全量：后端 `pytest tests/ -q` = **630 passed**（597 基线 + 33 新增）；
  前端 `node --experimental-strip-types --test` 三文件 = 35 passed；
  `tsc --noEmit` 通过。本 app 无 ESLint 交互配置，`next lint` 不能非交互运行。

### 17.9 Wrong vs Correct

```python
# Wrong — 沿用 compute_risk_metrics 的 inner join → 历史窗口被基准截断
joined = pd.concat([r_p.rename("p"), r_b.rename("b")], axis=1, join="inner")
sharpe = _ratio_annualized(joined["p"] - rf)
# Correct — 纯净值：走势页不 join 基准，全窗口 3 年样本
w = r_p[(idx >= end - 1095d) & (idx <= end)]
sharpe = _ratio_annualized(w - rf_daily_aligned)
```

```tsx
// Wrong — <Link href="/funds/sharpe-trend"> 变 /funds/funds/... 404
// Correct — 相对 basePath
<Link href={`/sharpe-trend?code=${code}`}>
```

---

## 18. 夏普榜单 v2：三道门 + 52 周窗口（11-13-sharpe-board-v2-rules，2026-11-13）

### 18.1 Scope / Trigger

触发本节的条件：改 v2 profile / `entry_predicate` 三道门 / `freeze_peer_rows` /
发布侧 peer 合并 / 52 周窗口聚合 / 榜单 DTO 新字段 / v1 迁移脚本任何一处。
设计依据与生产数据实测见 `.trellis/tasks/11-13-sharpe-board-v2-rules/research/v2-gate-impact.md`。

### 18.2 v2 入选规则（profile 版本隔离）

`SHARPE_BOARD_PROFILES` 新增 `(stock, v2)` / `(discovery-stock, v2)`，
**v1 两条一字不改**（v1 历史周行的 `profile_json` 按当时规则冻结，改 v1 常量会让
新读到的 profile 与已落库快照不一致）。v2 是 v1 的超集：

```python
_V2_EXTRA_FILTERS = {
    "min_ir": 0.5,           # 信息比率（跑赢基准效率）
    "min_sample_days": 700,  # 3 年约 750 交易日，留缺口余量
    "max_peer_pct": 20.0,    # 近 3 年同类排名前 20%
}
ALGORITHM_VERSION_V2 = "risk-3y-v2"
```

- 默认值三处同步切 v2：`weekly_refresh.BOARD_PROFILE_VERSION`、
  `api/sharpe_board.py` 的 `profile_version`、`aggregate_board` 默认参数。
- **回滚规则只需改 `BOARD_PROFILE_VERSION` 一行**（v1 profile 完整保留）。
- 实测叠加影响（2026-11-02 周）：stock 29→10、discovery-stock 68→33，不空榜。
- 被否决的两条（勿重提）：规模 ≤100 亿（只影响 2 只，且逻辑不成立）、
  连续性门槛进入选规则（只筛 1~3 只，降级为展示统计）。

### 18.3 `entry_predicate` 三个新参数（向后兼容铁律）

```python
entry_predicate(..., min_ir=None, min_sample_days=None, max_peer_pct=None)
```

- 三个参数默认 `None` = **整段跳过**，v1 profile 调用逐字节不变（由回归测试锁）。
- NULL 一律不命中；`max_peer_pct` 用 `<=`（含等号，前 20% ↔ 20.0）。
- **谓词是纯函数，不依赖 `date.today()`**：同类排名的 90 天陈旧过滤、格式校验
  全在 `freeze_peer_rows` 取值阶段完成，谓词只做数值比较。这样等价性测试可重现。

### 18.4 peer 数据必须冻结（与 `dd_3y` 同一个坑）

`fund_achievement_rank` 会被市场链路 L5 `delete + bulk insert` 覆盖重写。
发布时回读该表会拿到**下一轮**数据。唯一正确做法：

```python
freeze_peer_rows(db, codes) -> {code: {"peer_pct", "peer_raw", "as_of"}}
```

- 一次批量 `in_` 查询（500 codes 分块），**禁止 per-code 查询**。
- 无记录 / `peer_rank` 格式异常 / `as_of_date` 超 90 天 → 不入字典（= 无数据，不命中）。
- **陈旧判定用数据自带 `as_of_date`**，不是发布日：`refresh_service.py` 用
  `out["achievement_as_of_date"] = ref.date()`（取数参考日）而非 `today()`。
- 冻结进 `capture.peer_rows`；发布只读冻结，evidence_json 里存 `peer` 快照。

**两条链路冻结位置不同**（design §11，早一行就是过期数据）：

| 链路 | achievement 写入时机 | 冻结位置 |
|---|---|---|
| stock（雪球 yaml） | `snapshot_fund(fetch_ranking=True)` → `persist_snapshot` 主循环内 | 主循环**之后**，与 `freeze_dd_rows` 同处 |
| discovery-stock（市场） | **L5** `refresh_market_achievement` | **L5 之后**（L3 的 `freeze_dd_rows` 处还没跑 L5） |

### 18.5 既有缺陷修复：`BASE_ROW_FIELDS`

```python
BASE_ROW_FIELDS = ("name", "market_subtype", "age_years", "size_yi",
                   "mgr_experience_years", "mgr_experience_years_max")
```

`min_mgr_exp` 优先读 `_max`（共管取最长），缺了该列会静默回退到取最短而误杀
「老将+新人」组合。实测修复前 0/97 的观测证据里带此字段。
**改这个字段会改变 `evidence_json` 结构**——已有测试断言改为「包含关键字段」
而非全等（否则每次加字段都会挂）。

### 18.6 发布侧诊断 `gate_missing`

区分「数据缺失」与「不达标」：缺失进 `diagnostics["gate_missing"]`（按门分桶），
不达标是正常筛选结果**不进诊断**（否则淹没真正的采集问题）。

### 18.7 52 周窗口（统计 + 图表统一卡一年）

```python
WINDOW_WEEKS = 52
_RANGE_WEEKS = {"all": 52, "1y": 52, "6m": 26, "3m": 13}
def _window_start(current): return current - timedelta(weeks=WINDOW_WEEKS - 1)
```

- **364 = 52×7 恰是 7 的倍数**，窗口起点天然落在周一网格。
  旧 `_RANGE_DAYS["1y"] = 365`（52 周+1 天）会让起点落周日、series 全 null
  （§13 记录的 2026-11-05 真实回归）——改用整周数后该缺陷自然消失。
- `listed_weeks` / `consecutive_weeks` / `latest_sharpe` / `near_12w` 全部
  **只统计窗口内**；窗口外仍有观测的基金 `listed_weeks=0` → 被默认
  `min_weeks=1` 筛掉（预期连带后果，实测 13 只被挤出视图）。
- **窗口只作用于聚合，不删除任何观测行**（AC9c）。
- `range` 语义收窄为**窗口内缩放**：起点 `max(window_start, range_start, first_obs)`，
  绝不让用户看到超出 52 周的数据；`all` 与 `1y` 等价。
- `QUALIFIED_SHARPE = 0.8` 是展示用的绝对参考线，与 v2 `min_sharpe` 解耦。

### 18.8 DTO 新字段（三处同步，§3a 静默砍字段陷阱）

`SharpeBoardItemDTO` / `SharpeBoardItem` / 页面三处同步新增：
`near_12w_qualified` / `near_12w_total` / `peer_pct` / `peer_as_of`。
**`aggregate_board` 的 `item_keys` 元组必须同步加字段**，否则被过滤掉。

`peer_as_of` 是 ISO **字符串**（来自 evidence_json），不是 date 对象。

### 18.9 已知排序陷阱

窗口外基金 `latest_sharpe=None`，`min_weeks=0` 时可能进 `matched`。
**排序键必须对 None 取 `-inf`**，不能写 `-s["latest_sharpe"]`（TypeError）：

```python
def _sort_key(s):
    sh = s["latest_sharpe"]
    return (-s["listed_weeks"], -sh if sh is not None else float("-inf"), s["code"])
```

### 18.10 v1 历史处置（迁移脚本）

`scripts/migrate_v1_archive.py` 三阶段，**默认 dry-run**：

1. 导出 v1 weeks（全 status）+ observations → JSON + SQL + manifest(sha256)
2. 验证：重读比对行数/哈希；临时库重放 SQL 比对
3. 删除：**仅 `--apply` 执行**；单事务，先删 observations 再删 weeks

- 存档落 `data/archive/`（不入 git），可完整恢复。
- **部署顺序**：代码上线（版本仍 v1）→ 跑迁移 → 切 `BOARD_PROFILE_VERSION=v2`。
  不能边删边写新 v1 行。
- **不做历史回溯**：v2 三道门里「同类排名前 20%」历史上根本不存在
  （`fund_achievement_rank` 只有 6 个 `as_of` 快照，非时序）。强行用今日快照
  回填历史周 = 前视偏差，`listed_weeks` 会系统性偏乐观。v2 从上线周干净积累。

### 18.11 Tests Required

- `tests/test_filter_service.py::TestV2EntryGates`：三道门边界/等号/NULL/组合/默认 None 回归
- `tests/test_sharpe_board_service.py::TestV2Profiles`：v1 不被污染、v2 是 v1 超集、版本升级
- `tests/test_sharpe_board_service.py::TestV2PublishGates`：三道门拦截、gate_missing 诊断、v1 兼容
- `tests/test_sharpe_board_service.py::TestFiftyTwoWeekWindow`：100 周封顶 52、周一网格、
  不足 52 不补零、range 别名、近12周达标、peer 展示、窗口不删数据
- `tests/test_sharpe_board_capture.py::TestFreezePeerRows`：解析/90 天陈旧/格式异常/500 分块
- `tests/test_sharpe_board_capture.py::TestV2PeerFreezeWiring`：stock 链路冻结
- `tests/test_migrate_v1_archive.py`：导出→验证→删除→恢复、只删 v1、dry-run 不删
- 前端 `sharpe-board.test.ts`：默认 v2、describeEntryFilters 三道门、URL 往返

全量：后端 **668 passed**（630 基线 + 38 新增）；前端 37 passed + `tsc --noEmit` +
`pnpm build` 通过。

### 18.12 Wrong vs Correct

```python
# Wrong — 发布时回读会被 L5 覆盖的共享表
peer = db.get(FundAchievementRank, code).peer_rank
# Correct — 只读本轮冻结的 capture.peer_rows
peer = capture.peer_rows.get(code)

# Wrong — 谓词里读 date.today()（测试不可重现）
if (today - as_of).days > 90: return False
# Correct — 陈旧过滤在 freeze_peer_rows 完成，谓词只比数值
if v is None or v > max_peer_pct: return False

# Wrong — 365 天裁剪起点落周日，series 全 null
start = current - timedelta(days=365)
# Correct — 52 个整周，起点天然周一
start = current - timedelta(weeks=51)
```

---

## 19. 夏普榜单 v3：年度同类排名口径 + 历史回溯（11-14-sharpe-board-v3-yearly-peer，2026-11-14）

### 19.1 Scope / Trigger

触发本节：改年度门槛 / `freeze_yearly_peer_rows` / `yearly_window` /
回溯脚本 / v3 profile 任何一处。设计依据见任务 `research/yearly-rank-interface.md`。

### 19.2 为什么换口径（核心事实）

`ak.fund_individual_achievement_xq` 返回两类排名，性质截然不同：

| 类型 | period_kind | 性质 | 能否回溯 |
|---|---|---|---|
| 年度业绩 | `年度业绩` | 某自然年的**最终**排名，历史固定值 | ✅ |
| 阶段业绩 | `阶段业绩` | 滚动窗口（「截至今天」），每次调用会变 | ❌ |

**实测证据**：库内 `as_of=2026-09-09` 写入的 2023 年排名（`3456/4165`）与
2026-11-14 实时接口值**逐字一致**。这是 v3 敢做历史回溯的唯一根据。

v2 用滚动分位（`阶段业绩/近3年`），历史上不存在 → 榜单只能从上线周积累（只有 1 个点）。
v3 换成年度排名 → 每周判定都能用同一份历史数据复现 → 可补满历史曲线。

### 19.3 门槛定义

```python
YEARLY_PERIOD_KIND = "年度业绩"
YEARLY_WINDOW = 3             # 最近 3 个「已完成」自然年度
MIN_YEARLY_TOP_PCT = 25.0     # 单年分位 ≤25% 算该年达标
MIN_YEARLY_YEARS = 2          # 3 年中至少 2 年达标

def yearly_window(ref_year):   # 2026 → ["2023","2024","2025"]
    return [str(y) for y in range(ref_year - 3, ref_year)]
```

- **排除当年**：当年未结束，年度排名是「今年以来」的不完整值，与完整年度不可比。
- **不做 `as_of` 陈旧判断**：年度排名是历史事实，不存在过期
  （v2 的 `PEER_STALE_DAYS=90` 只适用于滚动口径）。
- 缺失年份记 `None`，不计入达标年数。

### 19.4 `freeze_yearly_peer_rows`（唯一 peer 数据来源）

```python
freeze_yearly_peer_rows(db, codes, *, ref_year=None,
                        top_pct=25.0, min_years=2) -> dict[str, dict]
# {code: {"years": {"2023": 8.2, "2024": None, "2025": 12.5},
#         "qualified_years": 2, "yearly_top_pct": 25.0,
#         "min_years": 2, "qualified": True, "window": [...]}}
```

- 一次批量 `in_` 查询（500 分块），禁止 per-code。
- **`qualified` 在冻结时算好**，不在谓词里算：阈值随 profile 版本变，
  把「当时用什么阈值、算出了什么」一并冻结，符合 §13「发布只读本轮证据」。
- 窗口内**全部年份都无有效排名**的 code 不入字典（无证据 → 发布侧计 `gate_missing`）。

### 19.5 谓词参数与不可混用的警告

```python
entry_predicate(..., min_yearly_years=None)   # v3：只读 qualified_years
```

- 只读冻结好的 `qualified_years`，保持纯函数。
- **`min_yearly_top_pct` 不是谓词参数**——它是冻结阈值，已随 peer_rows 固化。
  发布侧必须过滤掉它再传给 `entry_predicate`（否则 TypeError）。
- **不可与 `max_peer_pct` 混用**：后者是滚动口径「单个分位 ≤ X」，
  前者是「N 年中 M 年达标」，语义完全不同。同一个参数名在不同版本表示不同
  含义会让排障极难，故 v3 profile 不含 `max_peer_pct`。

### 19.6 v3 profile

`_V3_EXTRA_FILTERS = {min_ir: 0.5, min_sample_days: 700,
                      min_yearly_top_pct: 25.0, min_yearly_years: 2}`

- `ALGORITHM_VERSION_V3 = "risk-3y-v3"`；默认版本切 v3（周任务/API/聚合三处）。
- v1 / v2 profile **一字不改**，历史周行按版本隔离。
- 实测影响（2026-11-14，36 只 v2 成员）：前25%至少2年 → 保留 29 只（81%）。

### 19.7 历史回溯脚本

`scripts/backfill_v3_yearly_peer.py`（基于 `backfill_sharpe_board_ext.py`）：

| 项 | v1 ext 脚本 | v3 脚本 |
|---|---|---|
| profile | v1 | v3 |
| risk_rows | 只存 sharpe | **补 ir + sample_days**（v3 门槛需要） |
| peer 数据 | 无 | `freeze_yearly_peer_rows`，**一次冻结全周共享** |

- **夏普/IR/样本天数必须按周算**（当周往前 3 年窗口），不能用今天的值——
  那正是 v2 里拒绝的前视偏差。
- **年度排名全周共享不构成前视偏差**：它是已发生的历史事实。
- 幂等：已存在 complete 周的 `(source, v3, week)` 由 `publish_week_board` 跳过。
- 默认 dry-run，`--publish` 才写库；净值/基准 pickle 缓存复用一次网络拉取。

### 19.8 展示（DTO 三处同步）

v2 的 `peer_pct`（单值滚动分位）保留以支持 `?profile_version=v2` 查询；
v3 新增：
- `peer_years: dict[str, float|null]` — 各年分位
- `peer_qualified_years: int|null` — 达标年数
- `peer_window: list[str]|null` — 评估年度

前端「同类分位」列：有 `peer_qualified_years` 时渲染 `2/3 年`（hover 显示各年明细），
否则回退 v2 的 `前 X%`。

### 19.9 Tests Required

- `test_sharpe_board_capture.py::TestYearlyWindow`：窗口滚动/升序/默认常量
- `test_sharpe_board_capture.py::TestFreezeYearlyPeerRows`：3年/2年/1年达标、
  缺年、边界 25.0%、超界 25.01%、格式异常、**as_of 陈旧仍有效**、窗口外年份忽略、
  500 分块、自定义阈值
- `test_filter_service.py::TestV3YearlyGate`：边界/NULL/默认 None 回归/不看 peer_pct
- `test_sharpe_board_service.py::TestV3Profiles`：v1/v2 未污染、三版本 algorithm 互异
- `test_sharpe_board_service.py::TestV3PublishGates`：达标/部分达标入选、evidence 明细、
  v2 忽略年度参数
- `test_backfill_v3.py`：dry-run 不写、周键周一、evidence 含年度、幂等、**v2 数据零影响**

全量：后端 **705 passed**（668 基线 + 37 新增）；前端 38 passed + `tsc --noEmit`。

### 19.10 Wrong vs Correct

```python
# Wrong — 把冻结阈值当谓词参数（TypeError）
predicate = entry_predicate(**profile["filters"])
# Correct — 过滤掉冻结专用参数
kw = {k: v for k, v in profile["filters"].items() if k != "min_yearly_top_pct"}
predicate = entry_predicate(**kw)

# Wrong — 用年度排名的「当年」数据（不完整年度，与完整年不可比）
window = [str(y) for y in range(ref_year - 3, ref_year + 1)]
# Correct — 排除当年
window = [str(y) for y in range(ref_year - 3, ref_year)]

# Wrong — 回溯时夏普用今天的值（前视偏差）
risk_rows[code] = {"sharpe": db.get(FundRiskMetrics, code).sharpe}
# Correct — 按当周往前 3 年窗口重算
m = compute_risk_metrics(r_p_windowed, r_b_windowed, rf)
```

---

## 20. 基金代码快速搜索：lookup 路由判定（11-14-fund-code-quick-search，2026-11-14）

### 20.1 Scope / Trigger

触发本节：改 `lookup_service.resolve_tab` 的判定优先级 / `/lookup/{code}` 路由 /
`FundCodeSearch` 组件任何一处。

### 20.2 判定优先级（yaml 名单优先于 market_type）

```
1. 在 funds.yaml（债基精选 31 只）        → bond
2. 在 funds_stock.yaml（股基 142 只）     → stock
3. market_type 以「债券」开头              → discovery-bond   ← 含脏值防御
4. market_type == 'stock'                  → discovery-stock
5. market_type == 'other' + subtype 属债券 → discovery-bond
6. 其余（other+混合/FOF/货币/空，或未知）  → discovery-stock
7. 库内无该 code                            → found=False
```

**为什么 yaml 优先**：yaml 是精选名单，名单内的基金用户多半从对应雪球 tab 认识；
market_type 是全市场粗分类。两份名单无交集（实测 31 / 142 / 交集 0）。

**为什么 `other` 必须再看 subtype（实测关键陷阱）**：生产库 `other` 有 5115 只，
其中 **2653 只 `market_subtype` 是「债券型-*」**。若笼统兜底到股基市场，
这两千多只会跳到错误 tab。必须先用 `DISCOVERY_BOND_SUBTYPES` /
「债券」前缀判定。

**脏值防御**：`market_type` 有一行被误写成 `'债券型-长债'`（code=519622，
是 subtype 的值写进了 type 字段）。凡以「债券」开头一律按 bond。

### 20.3 API 契约

`GET /api/funds/lookup/{code}`，`code` 必须 6 位数字（`pattern=r"^\d{6}$"`）。

```python
class FundLookupResponse(BaseModel):
    code: str
    found: bool
    name: Optional[str] = None
    tab: Optional[str] = None          # bond|stock|discovery-bond|discovery-stock
    market_type: Optional[str] = None
    in_yaml: Optional[str] = None      # 'bond'|'stock'|None
    path: Optional[str] = None         # '/discovery-stock?code=002910'
```

- **查不到（found=False）返回 200**，不是 404：这是业务结果，不是错误。
  返回 404 会让前端必须区分「代码不存在」与「接口挂了」。
- **格式非法返回 422**：那是调用方 bug，应明确暴露。
- **`/lookup/{code}` 必须注册在通用 `/{code}` 之前**（契约 §13 同一类陷阱）。

### 20.4 `path` 是相对路径（basePath 契约）

返回值 `path` **不带 `/funds` 前缀**——前端用 Next router 跳转时 Next 会自动补
basePath；写 `/funds/...` 会变成 `/funds/funds/...` 404（§4 已记录该陷阱）。

**11-16 起 `path` 的形式变了**（代码搜索改为「列表出结果」）：

```
tab=bond            → /bond?search_code=003547
tab=stock           → /stock?search_code=002910
tab=discovery-bond  → /bond?search_code=...      ← 收敛到合并页
tab=discovery-stock → /stock?search_code=...     ← 收敛到合并页
```

- `tab` 字段语义**不变**（仍是四值分类，经理页徽章等复用）。
- `discovery-*` 直接给合并页：它们只是 redirect 壳，经壳会多一跳且把
  `source=market` 留在 URL 里（退出搜索后用户莫名处在「市场」分段）。
- **`search_code=` ≠ `code=`**：前者是「列表锁定这一只、点行才开抽屉」，
  后者是「直达并自动开抽屉」（经理页徽章）。两个参数各管一件事，互不覆盖。

### 20.5 前端接入

- 搜索框在筛选 chip 行右侧（`FilterChipBar` 的 `showCodeSearch`），
  经理 / 夏普榜单 / 走势页不显示。
- **搜索态是 URL 状态**：`?search_code=<6 位>`，与筛选参数**并存**
  （进入/退出搜索都不动任何筛选维度）。解析与序列化在 `lib/search-code.ts` +
  `lib/useFilters.ts`。
- **落点 URL 必须由 `buildSearchHref` 拼，不能直接 `router.push(res.path)`**：
  后端 `path` 只有 `search_code`，直接 push 会把当前筛选整串丢掉（实测踩到）。
  规则：同页保留当前查询串（替换 `search_code`、`page` 归 1）；跨页只带
  `search_code`；两者都清掉互斥的 `code` / `focus`。
- **搜索态不参与 `activeCount`**：它有自己的 chip（「代码搜索 XXX ×」），
  混进筛选计数会让「筛选(3)」与实际维度对不上。
- 退出搜索的三个触发：点 chip ×、改任一筛选维度/分类/来源/每页条数、
  点「清空」。**不退出**：翻页、改排序。
- `FundTable` 用 `highlightCode` 高亮命中行（accent 竖条 + 浅底，与对比选中的
  整行 info-tint 区分，两者可叠加）；`emptyHint` 给搜索空结果文案。
- 搜索态隐藏 `Pagination`（结果只有 1 行）。

### 20.6 Tests Required

- `test_lookup_service.py`：六级优先级全覆盖，重点 `other`+债券型 → discovery-bond
- `test_lookup_api.py`：200/422 语义、**路由不被 `/{code}` 吞**、7 字段透出、
  `path` 用 `search_code=` 且 discovery-* 收敛到合并页
- `test_code_search.py`（11-16）：`/screen?code=` 与 `/stock/screen?code=`
  单条命中、**阈值被忽略**、`is_active=false` 仍返回、宇宙外仍返回、
  不存在 code → total=0、非法 code → 422、不带 code 时老链路不变
- `src/lib/lookup.test.ts`：归一化（trim/全角/夹字符）、6 位校验、状态分类
- `src/lib/search-code.test.ts`（11-16）：`parseSearchCode` /
  `searchCodeApiQuery`（只发 `code=`）/ **`buildSearchHref` 保留筛选**、
  跨页只带 `search_code`、清互斥参数

全量（11-16 后）：后端 **769 passed**（733 基线 + 23 新增 + 13 个 path 断言更新）；
前端 74 passed + `tsc` + `build`。

### 20.7 Wrong vs Correct

```python
# Wrong — other 一律兜底股基市场（2653 只债基跳错 tab）
if mtype == 'other': return 'discovery-stock'
# Correct — other 按 subtype 细分
if mtype == 'other':
    if msub in BOND_SUBTYPES or msub.startswith('债券'): return 'discovery-bond'
    return 'discovery-stock'
```

```tsx
// Wrong — path 加了 /funds 前缀，变 /funds/funds/... 404
router.push(`/funds${res.path}`)
// Wrong — 直接 push 后端 path：把当前筛选整串丢掉（实测：筛着规模 ≥5 亿，搜完回来没了）
router.push(res.path)
// Correct — 相对路径交给 Next 补 basePath，并让 buildSearchHref 决定筛选去留
router.push(buildSearchHref(res.path, window.location.search, window.location.pathname))
```

```python
# Wrong — 找不到返回 404（前端要区分业务未命中与接口故障）
raise HTTPException(404)
# Correct — 200 + found=False
return {"code": code, "found": False, "path": None, ...}
```

### 20.8 代码搜索语义：`/screen?code=` 故意不套阈值

`GET /api/funds/screen?code=003547`、`GET /api/funds/stock/screen?code=003547`
走 `FilterService.search_by_code(code, curated_kind)`：

| 维度 | 行为 | 理由 |
|---|---|---|
| 阈值（age/size/dd/mgr/sharpe/exclude_qdii） | **全部忽略** | 搜的是「库里这一只」，不是「当前筛选命中的这一只」；否则用户搜 002910 却因规模 4.9 亿看不到结果，会以为代码错了 |
| `is_active` | **不要求** | 代码搜索是查询动作，已清盘基金也该能点开看历史 |
| 当前 tab 宇宙 | **不要求** | 正常路径前端已先经 lookup 判 tab；这里只认 code |
| 排序/分页 | 不生效（结果 ≤1 条） | — |

返回结构与 `/screen` 同构（`{total, items}`，条目带 `in_curated`），
表格与文案因此完全复用。**不要**把 `code` 分支塞进 `_screen`：`_screen`
承担排序/分页/宇宙语义，加单条特例会污染 6 个调用点。

## 21. 夏普榜单数据缺口周口径（11-14-sharpe-board-gap-weeks，2026-11-14）

### 21.1 Scope / Trigger

节假日休市（春节等）会让某一周的**风险样本尾日没有前进**（停在上一周的交易日），
该周发布结果因此不是「这只基金没达标」，而是**数据不可用**：

| 来源 | 2026-02-16 实测 | 含义 |
|---|---|---|
| stock（雪球三分法） | `skipped_no_new_data`，`selected_count=0` | 整周没发榜 |
| discovery-stock（市场） | `complete`，但只入选 2 只（正常周 19~44 只） | 发了榜，但 38 只候选样本未更新 |

旧口径把这两周都算成「缺席」→ 连续周数被数据缺失打断（`003598` 显示 51 在榜 /
38 连续），把**数据缺一周**误读成**表现断档**。本节定义缺口周口径。

### 21.2 判定模型（三态）

窗口内每个 (基金, 周) 归为三类：

| 类别 | 判定 | 计入在榜 | 中断连续 |
|---|---|---|---|
| `listed` 在榜 | 该周有该基金观测 | ✅ | 否 |
| `gap` 数据缺口 | 该基金该周**没有有效样本**：该来源该周没有 complete 榜（failed / skipped_no_new_data / 未跑），**或** 该基金在该周该来源的 `diagnostics.stale_codes` 里（样本尾日未前进） | ❌ | **否**（跳过） |
| `miss` 可评缺席 | 发了 complete 榜、该基金样本新鲜，却没进榜 | ❌ | **是** |

信号全部取自库里已有事实，无新阈值、无启发式：

- 周是否发榜 → `sharpe_board_weeks.status`；
- 基金样本是否更新 → 同周 `sharpe_board_weeks.diagnostics_json.stale_codes`
  （发布侧第 6 步写入：入选谓词通过但样本尾日未前进的基金）。

实测：窗口内除 2026-02-16 外所有周 `stale_codes` 为空 → 信号稀疏且精确。

**source=all 的合并**：`gap` = **所有**在册来源都缺口（stock 没发榜 + discovery-stock
该基金 stale → gap）；任一来源能给出有效样本即为可评（miss 判定）。

### 21.3 统计口径

| 字段 | 定义 |
|---|---|
| `listed_weeks` | 窗口内在榜周数（**分子，排序键不变**） |
| `evaluable_weeks`（新） | 窗口内该基金**有有效样本**的周数 = 52 − 缺口周数（**分母**） |
| `consecutive_weeks` | 从最近上榜周逐周 -7 天回退：在榜记 1；**缺口周跳过**（不计数、不中断）；miss 周中断 |
| `gap_weeks`（新，列表项） | 该基金**在榜期间**的缺口周（ISO 日期；上榜前的缺口与它无关，不列） |

`consecutive_weeks` 仍是「在榜周数」的连续段长度（缺口周不在榜，不计入长度）。

`003598` 实测结果：在榜 51 / 可评 51 / 连续 51 / 缺口周 ['2026-02-16'] → 前端显示
**51/51**。`008261`（2026-03-30 真实缺席）在榜 50 / 可评 51 / 连续 32 —— 真实缺席
仍然中断连续。

### 21.4 DTO（三处同步，§3a 静默砍字段陷阱）

- `SharpeBoardItemDTO`：`evaluable_weeks: int = 0`、`gap_weeks: list[date] = []`；
- `SharpeBoardDiagnosticsDTO`：`gap_weeks: list[date] = []`（**周级**缺口周）；
- `aggregate_board` 的 `item_keys` 元组必须同步加两个字段，否则被过滤掉。

`diagnostics.gap_weeks`（周级）与既有 `no_board_weeks` 并存、语义不同：

- `no_board_weeks` = 周历内**没发 complete 榜**的周；
- `gap_weeks` = 周历内**数据不可用**的周 = 没发榜 **或** 该周任一来源有基金样本未更新。

### 21.5 陷阱

1. `week_meta` 必须按 **(source, week_start)** 建键——`all` 模式同周两行，用单键会串。
2. `stale_codes` 解析要容错（`diagnostics_json` NULL / 非 dict / `stale_codes` 非 list
   → 空集），一条脏数据不得让整页聚合失败。
3. `missing_evidence`（nav 失败）**不算**缺口周：当周若 complete 而某基金缺证据，
   它只是没参评，视同 miss（保守口径，与旧行为一致）。
4. 排序键仍用 `listed_weeks`（分子）——改分母不重排榜单。
5. 只读聚合层修正，**不改历史周行/观测行**；回滚 = revert 代码。

### 21.6 Tests Required

- `test_sharpe_board_api.py::TestGapWeekSemantics`：
  stale 基金缺口周不打断连续 / 真实缺席仍中断 / 上榜前缺口不进 `gap_weeks` /
  `source=all` 需全部来源都缺口才算缺口；
- `test_response_fields_all_present` 补 `evaluable_weeks` / `gap_weeks` /
  `diagnostics.gap_weeks`（§3a 回归）。

### 21.7 Wrong vs Correct

```python
# Wrong — 任何缺席都中断连续（数据缺一周被当成表现断档）
while w in week_set and w >= window_start:
    consecutive += 1
    w -= timedelta(days=7)

# Correct — 缺口周跳过不中断，只有可评却缺席（miss）才中断
while w >= window_start:
    if w in week_set:
        consecutive += 1
    elif w not in gap_all:
        break
    w -= timedelta(days=7)
```

```python
# Wrong — 只看「该周有没有榜」，忽略「这只基金那周有没有新样本」
gap = week_status[w] != STATUS_COMPLETE
# Correct — 榜发了但该基金 stale，同样是缺口
gap = (week_status[w] != STATUS_COMPLETE) or (code in stale_codes[w])
```

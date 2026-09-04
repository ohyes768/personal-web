# fund-select 契约（API / DB / 缓存 / 前后端链路）

## 1. Scope / Trigger

任务 09-01-fund-select-v1-bond 新增跨层契约（FastAPI ↔ Next.js 代理 ↔ 前端表格/对比），且补回了预研缺失的费率 fetcher 契约。记录于此防止后续 session 漂移。

## 2. Signatures

### API（前缀 /api/funds，全部 GET）

| 路由 | 参数 | 返回 | 错误 |
|---|---|---|---|
| /health | - | `{status:"ok"}` | - |
| /screen | min_age, min_size_yi, max_dd_3y, min_mgr_exp（均可空）; sort; order; exclude_qdii（默认 false） | `{total, items:[FundListItem]}` 不分页 | sort 不在白名单→422 |
| /{code} | - | FundDetail（业绩+fees+holdings） | 404 |
| /refresh | limit 可空 | `{task_id, status:"started"}`（BackgroundTasks） | - |
| /refresh/status | task_id 可空（空=最近一次） | `{task_id,status,total,completed,failed,errors[]}` | 404 无记录 |
| /export/csv | 同 screen | text/csv + UTF-8 BOM + `filename=funds_YYYYMMDD.csv` | - |
| /stats | - | `{total,with_performance,with_fees,with_holdings,last_refresh_at}` | - |

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
- Base: `GET /screen` 无参 → `funds.yaml` ∩ is_active（约 31 只）
- Bad: `GET /screen?sort=name` → 422（白名单外）；`GET /999999` → 404

## 6. Tests Required

`backend/tests/`（含交叉泄漏回归）：
- `test_filter_service.py`：四维组合/边界/排序/LEFT JOIN 保留/is_active 排除
- `test_universe_isolation.py`：债基/股票 yaml 宇宙互不泄漏；`fund_type` 不是成员谓词
- `test_performance_service.py`：回撤算法（1.0→1.2→0.9 = -25%）/收益窗口/None 语义
- `test_api.py`：TestClient + in-memory 覆盖依赖；422/404/BOM；stats 按宇宙计数
- `test_data_fetchers.py`：31 份费率夹具契约、债券分类关键词、yaml 宇宙

**测试夹具注意**：in-memory SQLite + TestClient 必须用 `StaticPool`（单连接共享），否则 TestClient 线程看不到建表。

## 7. Wrong vs Correct

### Wrong
```python
q.filter(FundPerformance.dd_3y <= max_dd_3y)   # 库内负值，-4.47 <= 5 恒真，筛不掉
q.where(Fund.is_active == True)                # 债基 tab 会看到股票 refresh 写入的全部活跃基金
Fund.fund_type.like("股票型-%")                # 股票 tab 会吃到债基名单里的混合/QDII
init_db()  # 测试里对全局 engine 建表，但请求走 override session（另一 engine）
```
### Correct
```python
q.filter(FundPerformance.dd_3y >= -abs(max_dd_3y))  # 绝对值语义
q.where(Fund.is_active == True, Fund.code.in_(resolve_universe_codes("bond")))
# conftest: create_engine("sqlite:///:memory:", poolclass=StaticPool)
```

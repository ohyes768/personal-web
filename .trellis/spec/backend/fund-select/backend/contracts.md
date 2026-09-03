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
- `refresh_runs`：task_id PK，进度轮询数据源

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

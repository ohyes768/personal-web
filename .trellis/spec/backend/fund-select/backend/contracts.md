# fund-select 契约（API / DB / 缓存 / 前后端链路）

## 1. Scope / Trigger

任务 09-01-fund-select-v1-bond 新增跨层契约（FastAPI ↔ Next.js 代理 ↔ 前端表格/对比），且补回了预研缺失的费率 fetcher 契约。记录于此防止后续 session 漂移。

## 2. Signatures

### API（前缀 /api/funds，全部 GET）

| 路由 | 参数 | 返回 | 错误 |
|---|---|---|---|
| /health | - | `{status:"ok"}` | - |
| /screen | min_age, min_size_yi, max_dd_3y, min_mgr_exp（均可空）; sort; order | `{total, items:[FundListItem]}` 不分页 | sort 不在白名单→422 |
| /{code} | - | FundDetail（业绩+fees+holdings） | 404 |
| /refresh | limit 可空 | `{task_id, status:"started"}`（BackgroundTasks） | - |
| /refresh/status | task_id 可空（空=最近一次） | `{task_id,status,total,completed,failed,errors[]}` | 404 无记录 |
| /export/csv | 同 screen | text/csv + UTF-8 BOM + `filename=funds_YYYYMMDD.csv` | - |
| /stats | - | `{total,with_performance,with_fees,with_holdings,last_refresh_at}` | - |

### 关键语义

- **dd_3y 库内为负值**（如 -4.47）。用户阈值 `max_dd_3y=5` 按**绝对值**比较：SQL 用 `dd_3y >= -abs(max_dd_3y)`。前端展示原值（负号保留）。
- **fee_annual 是计算字段**：`fee_mgmt + fee_custody + (fee_service or 0)`；任一主字段缺失返回 null（不是 0）。
- **筛选宇宙 = `is_active==True` 全部**，不按债券类型过滤（31 只含混合/QDII 照常展示）。
- FundPerformance 用 **LEFT JOIN**：无业绩记录的基金保留在筛选结果（业绩列显示 null → 前端 "-"）。

### ORM（src/db/models.py）

- `funds`：code PK；age_years/size_yi/mgr_experience_years（Float 可空）；is_active 默认 True
- `fund_performance`：code PK；ret_1m/6m/1y/3y/5y + **dd_1y/3y/5y**（只有这三档回撤，无 dd_1m/dd_6m——performance_service 显式过滤）
- `fund_fees`：8 字段对齐预研 `cache/fees_{code}.json` 契约
- `fund_holdings_bond`：(code, report_date) 复合 PK
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
- `router.push` 用**相对路径**（`?${qs}` 或 `location.pathname`），Next 自动加 basePath
- 原生 `fetch('/funds/api/...')` **必须写全路径**——fetch 不吃 basePath

### Gotcha: 代理剥 BOM

代理 route 用 `res.text()` 会吞掉 CSV 的 UTF-8 BOM（TextDecoder 默认去 BOM）。**用 `res.arrayBuffer()` 二进制透传**。

## 5. Good/Base/Bad Cases

- Good: `GET /screen?max_dd_3y=5` 返回 dd_3y∈[-5,0] 的基金
- Base: `GET /screen` 无参 → 全部 is_active（31 只）
- Bad: `GET /screen?sort=name` → 422（白名单外）；`GET /999999` → 404

## 6. Tests Required

`backend/tests/`（41 个，覆盖率 62% ≥ 60% 门槛）：
- `test_filter_service.py`：四维组合/边界/排序/LEFT JOIN 保留/is_active 排除
- `test_performance_service.py`：回撤算法（1.0→1.2→0.9 = -25%）/收益窗口/None 语义
- `test_api.py`：TestClient + in-memory 覆盖依赖；422/404/BOM
- `test_data_fetchers.py`：31 份费率夹具契约、债券分类关键词、yaml 宇宙

**测试夹具注意**：in-memory SQLite + TestClient 必须用 `StaticPool`（单连接共享），否则 TestClient 线程看不到建表。

## 7. Wrong vs Correct

### Wrong
```python
q.filter(FundPerformance.dd_3y <= max_dd_3y)   # 库内负值，-4.47 <= 5 恒真，筛不掉
init_db()  # 测试里对全局 engine 建表，但请求走 override session（另一 engine）
```
### Correct
```python
q.filter(FundPerformance.dd_3y >= -abs(max_dd_3y))  # 绝对值语义
# conftest: create_engine("sqlite:///:memory:", poolclass=StaticPool)
```

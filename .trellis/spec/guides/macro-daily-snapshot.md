# Macro Daily Snapshot API Contract

> **Purpose**: 信号首页 · 日频区块的接口契约与跨层对齐约定。改动 3 维度指标清单、15:00 规则或回退语义前必读。
>
> **Last verified**: 2026-09-20
> 信号首页自 2026-08-31 起为单页双区块(月度 4 卡 + 日频 3 卡同屏,MacroSignalTab 挂载即并行请求,无模式切换/懒加载)
> 2026-09-01:日频 monetary_policy 组加 DR001(隔夜),来源 `prr-md.json`,与 DR007(7 天)并列展示;共 3 维度 8 指标。前端组标题日频模式显示「流动性」(月度模式仍为「货币政策」,后端 dimension key 仍为 `monetary_policy`,API 无变更)。详见 §2.1。
> 2026-09-15:修正 DR001 恒空 bug——`prr-md.json` 真实响应 `records` 在**顶层**(`data` 下仅 showDateCN/showDateEN),`extract_dr001` 此前按 `data.records` 解析导致自上线起解析永远失败、被失败隔离静默吞成 null;测试 mock 与代码同错,测试全绿但从未对过真实接口。详见 §2.1 响应结构小节。
> 2026-09-16:DR001 弃用 prr-md.json 实时旁路,改为 DR007 同款定时落库(`POST /update/dr001` → 同一 `prr-chrt.csv` 取 index 6 列 → `dr001.csv`),获得 asof 回退能力;prr-md 实时链路代码整体删除。详见 §2.1/§4。
> 2026-09-20:修正 `POST /update/dr001`「数据已落库但响应报失败」问题——新增更新端点的载荷类型必须同步加入共享 `UpdateResponse.data` 联合类型，并以端点级测试覆盖成功响应。详见 §7。
> **Source files**:
> - `backend/macro/src/services/daily_snapshot_service.py`(`_DAILY_INDICATORS` 指标清单)
> - `backend/macro/src/api/routes.py`(`GET /daily-snapshot`)
> - `apps/macro/src/app/modules/economic/components/macro-signal/constants.ts`(`DAILY_GROUPS`)
> - `apps/macro/src/app/modules/economic/components/macro-signal/DailyCardGrid.tsx`

---

## 1. 接口

```
GET /api/macro/daily-snapshot?date=YYYY-MM-DD   # date 可缺省
```

- nginx `/api/macro/` 剥前缀 → 后端 `/api/daily-snapshot`;本地 dev 由 next.config.js rewrites 代理
- `date` 缺省 → 后端按 15:00 规则推导(见 §3),响应 `data.date` 返回实际生效日期
- `date` 非法格式 → 400

## 2. 响应 shape

```jsonc
{
  "success": true,
  "data": {
    "date": "2026-08-28",          // 实际生效日期(= date 或推导结果)
    "dates": ["2026-08-28", "..."], // 降序,volume 序列近 60 个交易日 ∪ 今日
    "groups": {
      "monetary_policy": { "indicators": [
        { "key": "dr001", "value": 1.32, "prev_value": null, "data_date": "2026-09-01" },
        { "key": "dr007", "value": 1.36, "prev_value": 1.42, "data_date": "2026-09-01" }
      ] },
      "exchange_rate":   { "indicators": [...] },
      "risk_appetite":   { "indicators": [...] }
    }
  }
}
```

- `data_date ≠ 所选 date` 即发生了回退(前端行内灰字标注「实际 MM-DD」)
- `prev_value` = `data_date` 前一个有值日(前端算日变化,红涨绿跌);null 显示「—」

### 2.1 DR001 边界语义(2026-09-01 引入,2026-09-16 起定时落库)

- `dr001` = 银行间隔夜质押式回购加权利率(隔夜),与 DR007 **同源同文件**:`prr-chrt.csv`(GET,同 headers),取 `cols[6]`(DR001 加权利率;cols[7]=DR007、cols[8]=DR014,已与当日快照交叉验证)。解析要求 `len(cols)>=9` 且 float 可转,否则跳行(不猜测 8 列老格式列位)。
- **取数链路(2026-09-16 起,与 DR007 完全同款)**:scheduler `a_share_daily` 16:30 → `POST /update/dr001` → `dr001.csv`(合并去重升序) → `/daily-snapshot` 读 CSV asof 取值。首部署需手动触发一次 `/update/dr001` 全量回补(受 CSV 滚动窗口限制,约 3 个月)。
- 回退语义与 DR007 一致:外部源故障/当日未发布 → asof 回退最近可得值 + 行内标注;**不再**出现「实时拉取失败整行消失」(2026-09-16 前的旧行为)。
- `prr-md.json`(POST 当日快照)链路已退役删除——其历史教训保留:外部接口解析与测试 mock 不能互为依据,mock 按"想象的结构"构造会全绿但对不上真实接口(2026-09-15 DR001 恒空两周根因)。**新接外部数据源必须先用真实响应跑一次端到端验证,再以真实结构写 mock。**
- 仅日频快照展示:**不算 MA5、不跳转曲线**(无 INDICATOR_LINK_MAP 条目);该组日频模式组标题「流动性」,不渲染档位刻度。
- 前端展示:日频模式该组标题显示「流动性」(`DailyCardGrid.tsx` `DAILY_GROUP_TITLES` 覆盖);月度模式不受影响
- 该组在日频模式下**不渲染档位刻度**(与汇率/风险偏好两张卡一致,纯数据组)

## 3. 默认日期规则(15:00 规则)

- 本地时间 `< 15:00`(A股未收盘)→ 今日之前最近的 volume 交易日
- `≥ 15:00` → 今日(当日数据未入库时行级 asof 回退并标注)
- 规则**只在后端实现**:前端首拉不带 date、直接采纳响应 `date`,用户手动切换才显式传 date → 前后端规则天然一致,不要在前端复刻

## 4. 取数路径(重要)

**不要**用 `query_data_by_tab` 组装日频数据:该接口 `dates` 在含美债 Tab 上是美债交易日,不是日频卡用的 volume 并集;`us_treasuries` 本身不 reindex 到任意 union 轴。日频按索引 zip 仍会错位。`exchange_rates` 已对齐查询轴(与 china_bond/commodities 相同)。
日频走 `DataService` 原始 load 方法(`load_dr001`/`load_dr007`/`load_volume`/`load_data('exchange_rates')` 等),自己 dropna + asof(≤ 所选日期最后一个值)。
- `load_dr001` 与 `load_dr007` 同款:读各自 CSV(`dr001.csv`/`dr007.csv`),由 `/update/dr001`/`/update/dr007` 定时落库。两指标同源 `prr-chrt.csv`(DR001 取 `cols[6]`、DR007 取 `cols[7]`),解析服务 `dr001_service.py`/`dr007_service.py` 互为镜像

## 5. 跨层对齐约定(改指标必须三处同步)

| 后端 `_DAILY_INDICATORS`(daily_snapshot_service.py) | 前端 `DAILY_GROUPS`(constants.ts) | 前端 `INDICATOR_LABELS`(constants.ts) |
|---|---|---|
| indicator key | indicators 数组 key | label/单位/小数位翻译 |

- key 变更 → 三处同步 + `INDICATOR_LINK_MAP` 的曲线跳转映射
- CSV 数值列是中文列名(如 `美元指数`/`TED利差`),与英文 key 的映射只存在于 `_DAILY_INDICATORS`
- `monetary_policy` 组当前 key 列表(2026-09-01):`dr001`、`dr007`(`INDICATOR_LINK_MAP` 无对应条目,该组无曲线跳转入口)

## 6. dates 列表口径

`volume` 序列(A股交易日,每交易日必有值)近 60 个 ∪ 今日。以 volume 为交易日基准的原因:三张卡中 DR007/市场情绪均为 A股日历;美元/TED 指标在非美交易日的缺失由行级 asof 回退兜底。

## 7. 更新端点共享响应契约（2026-09-20）

### 1. Scope / Trigger

- 触发：新增或修改任何返回 `UpdateResponse` 的 `/api/update/*` 端点，尤其是端点携带新增的 `*UpdateData` payload 时。

### 2. Signatures

- `POST /api/update/dr001` → `UpdateResponse(data=DR001UpdateData(dr001=DR001Data(...)))`
- `UpdateResponse.data` 定义于 `backend/macro/src/models.py`，是显式联合类型。

### 3. Contracts

- 成功写盘后必须响应 `success=true`，且 `data.dr001.date`、`data.dr001.value` 可序列化。
- `DR001UpdateData` 必须是 `UpdateResponse.data` 联合类型的成员；仅定义模型或在路由中导入它都不足以满足响应契约。

### 4. Validation & Error Matrix

| 条件 | 预期结果 |
|---|---|
| `DR001UpdateData` 在联合类型中 | 保存成功后返回 `success=true` |
| 载荷类型漏入联合类型 | 数据可能已经写盘，但 Pydantic 校验失败，端点错误返回 `success=false`；scheduler 会把该项记录为失败 |

### 5. Good / Base / Bad Cases

- Good：路由返回的 `DR001UpdateData` 已登记在 `UpdateResponse.data`，调用方收到成功响应。
- Base：`data=None` 的“已是最新”响应仍可通过现有联合类型契约。
- Bad：新增 `FooUpdateData` 只在路由内构造，未加入 `UpdateResponse.data`，导致持久化和响应结果不一致。

### 6. Tests Required

- 对每个新增的更新 payload 写端点级测试：mock fetcher 返回一行有效数据，断言 HTTP 200、`success is True`、`data` 结构正确，并断言存储方法被调用。
- DR001 回归测试：`backend/macro/tests/test_dr001_update_response.py::test_update_dr001_returns_success_after_persisting_valid_data`。

### 7. Wrong vs Correct

#### Wrong

```python
# 只新增 DR001UpdateData 和路由返回值
return UpdateResponse(data=DR001UpdateData(dr001=latest))
```

#### Correct

```python
class UpdateResponse(BaseModel):
    data: Optional[
        DR007UpdateData
        | DR001UpdateData
        # ...other update payloads
    ] = None
```

路由端点测试必须验证此响应能通过 Pydantic 校验，而不只验证 `save_dr001_data` 已执行。

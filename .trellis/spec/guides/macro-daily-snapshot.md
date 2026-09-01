# Macro Daily Snapshot API Contract

> **Purpose**: 信号首页 · 日频区块的接口契约与跨层对齐约定。改动 3 维度指标清单、15:00 规则或回退语义前必读。
>
> **Last verified**: 2026-09-01
> 信号首页自 2026-08-31 起为单页双区块(月度 4 卡 + 日频 3 卡同屏,MacroSignalTab 挂载即并行请求,无模式切换/懒加载)
> 2026-09-01:日频 monetary_policy 组加 DR001(隔夜),来源 `prr-md.json`,与 DR007(7 天)并列展示;共 3 维度 8 指标。前端组标题日频模式显示「流动性」(月度模式仍为「货币政策」,后端 dimension key 仍为 `monetary_policy`,API 无变更)。详见 §2.1。
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

### 2.1 DR001 边界语义(2026-09-01 起)

- `dr001` = 银行间隔夜质押式回购加权利率,数据源中国货币网 `prr-md.json`(POST 接口,需 Referer + X-Requested-With 头)
- 仅当日快照:**不攒历史、不算 MA5、不跳转曲线**
- 失败隔离:`prr-md.json` 拉取失败 / DR001 字段缺失 → `dr001` 指标 `value`/`prev_value` 为 null,**不影响同组 DR007**
- 后端服务:`backend/macro/src/services/dr001_service.py`(`extract_dr001` 静态方法 + `fetch_today` 异步方法)
- 前端展示:日频模式该组标题显示「流动性」(`DailyCardGrid.tsx` `DAILY_GROUP_TITLES` 覆盖);月度模式不受影响
- 该组在日频模式下**不渲染档位刻度**(与汇率/风险偏好两张卡一致,纯数据组)

## 3. 默认日期规则(15:00 规则)

- 本地时间 `< 15:00`(A股未收盘)→ 今日之前最近的 volume 交易日
- `≥ 15:00` → 今日(当日数据未入库时行级 asof 回退并标注)
- 规则**只在后端实现**:前端首拉不带 date、直接采纳响应 `date`,用户手动切换才显式传 date → 前后端规则天然一致,不要在前端复刻

## 4. 取数路径(重要)

**不要**用 `query_data_by_tab` 组装日频数据:该接口 `dates` 在含美债 Tab 上是美债交易日,不是日频卡用的 volume 并集;`us_treasuries` 本身不 reindex 到任意 union 轴。日频按索引 zip 仍会错位。`exchange_rates` 已对齐查询轴(与 china_bond/commodities 相同)。
日频走 `DataService` 原始 load 方法(`load_dr001`/`load_dr007`/`load_volume`/`load_data('exchange_rates')` 等),自己 dropna + asof(≤ 所选日期最后一个值)。
- `load_dr001` 走 `prr-md.json`(POST 接口,与 `load_dr007` 的 `prr-chrt.csv` GET 接口不同),取 `records[productCode='DR001'].weightedRate`

## 5. 跨层对齐约定(改指标必须三处同步)

| 后端 `_DAILY_INDICATORS`(daily_snapshot_service.py) | 前端 `DAILY_GROUPS`(constants.ts) | 前端 `INDICATOR_LABELS`(constants.ts) |
|---|---|---|
| indicator key | indicators 数组 key | label/单位/小数位翻译 |

- key 变更 → 三处同步 + `INDICATOR_LINK_MAP` 的曲线跳转映射
- CSV 数值列是中文列名(如 `美元指数`/`TED利差`),与英文 key 的映射只存在于 `_DAILY_INDICATORS`
- `monetary_policy` 组当前 key 列表(2026-09-01):`dr001`、`dr007`(`INDICATOR_LINK_MAP` 无对应条目,该组无曲线跳转入口)

## 6. dates 列表口径

`volume` 序列(A股交易日,每交易日必有值)近 60 个 ∪ 今日。以 volume 为交易日基准的原因:三张卡中 DR007/市场情绪均为 A股日历;美元/TED 指标在非美交易日的缺失由行级 asof 回退兜底。

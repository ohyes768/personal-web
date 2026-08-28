# 技术设计:宏观信号首页 + 日频快照

## 1. 边界与文件清单

| 层 | 文件 | 动作 |
|---|---|---|
| 后端 | `backend/macro/src/services/daily_snapshot_service.py` | 新增:从 DataService 读序列,按日期取值组装快照 |
| 后端 | `backend/macro/src/api/routes.py` | 新增 `GET /daily-snapshot` 路由(挂在现有 router,对外 `/api/macro/daily-snapshot`) |
| 后端 | `backend/macro/src/models.py` | 新增 `DailyIndicator` / `DailyGroup` / `DailySnapshotData` / `DailySnapshotResponse` |
| 后端 | `backend/macro/tests/test_daily_snapshot.py` | 新增:默认日期规则、按日期取值、回退、日期列表 |
| 前端 | `apps/macro/src/lib/modules/macro-signal/types.ts` | 新增日频类型 `DailyMode` / `DailyIndicator` / `DailySnapshot` |
| 前端 | `apps/macro/src/app/modules/economic/components/macro-signal/constants.ts` | 新增 `DAILY_GROUPS`(3 组指标清单);`INDICATOR_LINK_MAP` 补日频指标跳转 |
| 前端 | `apps/macro/src/app/modules/economic/components/macro-signal/DailySwitcher.tsx` | 新增:日期切换器 |
| 前端 | `apps/macro/src/app/modules/economic/components/macro-signal/DailyCardGrid.tsx` | 新增:3 卡网格(内含单卡渲染,指标行较少不拆 DailyCard) |
| 前端 | `apps/macro/src/app/modules/economic/components/MacroSignalTab.tsx` | 改造:加 mode 状态 + 分段切换器;月度默认上个月;挂载日频分支 |
| 前端 | `apps/macro/src/app/modules/economic/page.tsx` | 改造:`macro-signal` 置首、label「信号首页」、activeTab 初始值 |

## 2. 后端接口契约

### `GET /api/macro/daily-snapshot?date=YYYY-MM-DD`

`date` 缺省时按规则推导:本地时间 `< 15:00` → 前一可用交易日,否则当日(非交易日/无数据则前移)。响应:

```jsonc
{
  "success": true,
  "data": {
    "date": "2026-08-28",          // 实际生效日期(= date 或缺省推导结果)
    "dates": ["2026-08-28", "...", "..."],  // 可选日期列表(降序,近 60 个,A股交易日 ∪ 今日)
    "groups": {
      "monetary_policy": { "indicators": [ /* DailyIndicator */ ] },
      "exchange_rate":   { "indicators": [ ... ] },
      "risk_appetite":   { "indicators": [ ... ] }
    }
  }
}
```

```python
class DailyIndicator(BaseModel):
    key: str                      # 与前端 constants 的 INDICATOR_LABELS key 一致
    value: float | None           # 所选日期(或回退)的值
    prev_value: float | None      # data_date 前一个有值日的值(算日变化用)
    data_date: str | None         # 实际数据日期;≠ 所选 date 即发生了回退

class DailyGroup(BaseModel):
    indicators: list[DailyIndicator]
```

要点:

- **取数路径(实现修正)**:原计划复用 `query_data_by_tab`,实现时发现其 `us_treasuries`/`exchange_rates` 段不 reindex 到 union 轴(序列与 `dates` 可能不等长,按索引 zip 会错位)。实际改为 `DataService` 原始 load 方法(`load_dr007`/`load_volume`/`load_data('exchange_rates')` 等)自行 dropna + asof 取值,契约不变。详见 `.trellis/spec/guides/macro-daily-snapshot.md` §4
- **dates 列表**:取 `volume` 序列最近 60 个交易日(它是每个 A股交易日都有值的序列),再 `∪ {今日}` 去重降序;volume 无数据时回退用 `dr007` 日期,仍无则空数组(前端切换器全禁用)
- **prev_value**:对每个指标,在窗口内取 `data_date` 之前的最后一个非空值;窗口内找不到则为 `None`(前端显示 `—`)
- **无数据日期**:date 不在 dates 里也允许查询(前端 ▶◀ 逐日步进可能落在非交易日),行为同样走 asof 回退;非法格式返回 400
- handler 用同步 `def`(pandas 读 CSV 阻塞,丢线程池,与 `/data` 路由同款注释与理由)

## 3. 前端设计

### 3.1 状态结构(MacroSignalTab 内)

```
mode: 'monthly' | 'daily'            // 分段切换器
selectedMonth: string                // 月度态(现有)
selectedDate: string | null          // 日频态;null = 首次进入,由 dates[0] 或 15:00 规则推导
```

- 两态独立 useState,互不重置(满足 R2)
- 日频数据 fetch 依赖 `[selectedDate]`;`selectedDate` 为 null 时不发请求,等 `dates` 就绪后推导默认值

### 3.2 默认值推导

- **月度默认上个月**:`prevMonth(now)`;若 `availableMonths` 就绪后不含它,取其中 `< 当月` 的最大者;全都不满足再回退现有逻辑(最大月份)
- **日频默认日期**:本地 `now < 15:00` → `今日之前最近的 dates 元素`;`≥ 15:00` → `今日(若今日在 dates 中,否则之前最近)`。dates 由首次 daily-snapshot 响应带回,推导后如与请求 `date` 不同需再拉一次;简化实现:首次请求不带 date,后端按同一规则推导,前端直接采纳响应的 `date` 字段 → 一次请求,前后端规则天然一致

### 3.3 DailySwitcher

结构与 `MonthSwitcher` 对称:`◀ 前一日` + 日期下拉(`MM-DD(今日)` 标注)+ `后一日 ▶`;禁用规则:到 `dates[0]`(最新)后禁用 ▶,到最旧后禁用 ◀;步进直接在 `dates` 数组内移动(天然跳过非交易日)。

### 3.4 DailyCardGrid / 指标行

- 网格:`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`,与月度一致
- 卡头:色点 + `GROUP_META[key].title` + 右侧 `N 项 · 截至 MM-DD`(取组内指标 `data_date` 的最大值)
- 指标行:`label + 📈(可选)` 左,右为 `value` 大字 + 日变化小字
  - 变化 = `value - prev_value`;`>0` 红 `▲x.xx`、`<0` 绿 `▼x.xx`、`=0`/prev 为空 `—`
  - 回退标注:`data_date ≠ 所选 date` 时,label 下方灰色小字 `(实际 MM-DD)`
  - 单位/小数位沿用 `getIndicatorMeta(key)`

### 3.5 DAILY_GROUPS 常量(前端展示顺序,后端同构)

```ts
DAILY_GROUPS = [
  { key: 'monetary_policy', indicators: ['dr007'] },
  { key: 'exchange_rate',   indicators: ['dollar_index', 'usd_cny', 'ted_spread'] },
  { key: 'risk_appetite',   indicators: ['volume', 'turnover', 'margin'] },
]
```

`INDICATOR_LINK_MAP` 补充:`dr007→rates`、`ted_spread` 已有;`volume/turnover/margin→market-sentiment`。其中 `volume/turnover/margin` 需在 `INDICATOR_LABELS` 补 label(两市成交额/换手率/融资融券余额,key 已存在同义中文映射,新增英文 key 别名即可)。

### 3.6 page.tsx 改动

- tabs 数组:`macro-signal` 移到 index 0,label「信号首页」,description「月度维度卡片 + 日频指标快照」
- `useState<TabType>('treasury-exchange')` → `'macro-signal'`
- `handleTabChange` 里无 macro-signal 分支,无需新增(它不用 timeRange)

## 4. 数据流

```
月度(不变):  skill 上传 → macro_signal_service → /api/macro/signal?month= → MacroSignalTab(monthly 分支)
日频(新增):  定时任务已落库的 CSV → DataService.query_data_by_tab(rates/treasury-exchange/market-sentiment, 45天窗口)
              → daily_snapshot_service 按 date asof 取值+prev → /api/macro/daily-snapshot → MacroSignalTab(daily 分支)
```

## 5. 取舍记录

- **不新建 `/data/daily` tab 拉全历史**:日频卡片只要两天值,新接口 45 天窗口足够,避免前端拉几 MB JSON 自己算
- **dates 用 volume 序列**:三张卡中 DR007/情绪都是 A股交易日口径,统一以 volume 为准;美元指标在非美交易日由 asof 回退兜底
- **15:00 规则放后端**:首次请求不带 date,避免前后端两套日期推导漂移;前端仅在用户手动切换时显式传 date
- **日频卡片不做档位刻度**:无 skill 评分,硬造刻度会误导
- **回滚**:前后端改动相互独立 —— 后端接口无人调用时无影响;前端日频分支依赖接口,接口异常走现有 error 态展示,不影响月度模式

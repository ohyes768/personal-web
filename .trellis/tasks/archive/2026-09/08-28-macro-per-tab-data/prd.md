# 宏观页按 Tab 拆读数与按需对比

## Goal

打开宏观经济页时，当前 Tab 只请求自己需要的序列；切到别的 Tab 再拉对应数据。对比页按已选指标按需请求。首次进入和刷新时，当前 Tab 内容区显示 loading。市场情绪等短序列用自己的日期轴，不再绑在美债交易日上。

## 背景

### 已有（不要重做）

仓库里已经有按 Tab 读数的骨架，前端也不再打总包：

- 后端 `GET /api/macro/data/{tab}` + `DataService.query_data_by_tab` + `TAB_SECTIONS` / `TAB_RESPONSE_FIELDS`
- 前端 `useTabEconomicData` → `economicApi.getTabData(tab)` → `/api/macro/data/${tab}`
- `page.tsx` 按 `tabDataMap[activeTab]` 把数据传给各图表 Tab
- 宏观信号仍走 `/api/macro/signal`，德债日债 Tab 已下线

规划阶段约定过 `GET /api/macro/data?tab=`。路径参数已经落地且与 `?tab=` 等价，**沿用 `/data/{tab}`，不再改成 query**。

### 还没做对的

1. **对比页仍拉全量**：`TAB_SECTIONS["comparison"] = None`，一切到对比就读全部 CSV。约定是 `indicators=dxy,us_10y,vix,gold` 按需拉，勾选再补。
2. **日期轴仍对齐美债**：`market-sentiment` 的 `TAB_SECTIONS` 仍含 `us_treasuries` 只为了 `dates`，再从响应里删掉美债。市场情绪 CSV 只有 2 个交易日时，曲线钉在 6 个月美债轴最右侧，看起来像没数。约定每个 Tab 用自己的日期轴。
3. **利率 Tab 缺美债 3M**：`TAB_RESPONSE_FIELDS["rates"]` 没有 `us_treasuries`，但 `RatesChart` 读 `data.us_treasuries['3m']`。
4. **前端缓存与约定不符**：约定内存 + 5 分钟 TTL；现实现是内存 + **1 小时 localStorage**（`CACHE_TTL_MS = 3600000`）。全量 JSON 写 localStorage 会碰到配额问题（性能任务已因此去掉总包缓存）。
5. **Loading 不够明显**：多数 Tab 只有一句灰字「加载中…」；中美利差用全屏 `LoadingOverlay`，挡住切 Tab。约定是**只盖当前 Tab 内容区**，带转圈，顶栏 Tab 仍可点。
6. **`GET /data/{tab}` 是 `async def`**：同步 pandas 会堵事件循环；总包 `GET /data` 已改成 `def` 丢线程池。

写入侧 `POST /update/*`、调度、宏观信号不在本任务范围。

## Requirements

### R1 业务 Tab 只返回本 Tab 字段

`GET /api/macro/data/{tab}` 继续作为各图表 Tab 的读数入口。响应只含该 Tab 的 `dates` + 序列字段。无效 `tab` 返回 400。

| tab | 响应字段 | 日期轴来源 |
|-----|----------|------------|
| treasury-exchange | dates, us_treasuries, exchange_rates, china_bond | 美债交易日 |
| liquidity-risk | dates, vix, tga, hibor | 本 Tab 序列日期并集 |
| rates | dates, us_treasuries, ted_spread, china_bond, dr007 | 本 Tab 序列日期并集 |
| commodities | dates, commodities | 商品日期 |
| stock-indices | dates, indices | 股指日期 |
| market-sentiment | dates, volume, turnover, margin | volume/turnover/margin 日期并集（A 股交易日） |

`macro-signal` 不是合法 `{tab}`。不带 `{tab}` 的 `GET /api/macro/data` 保留全量，页面不再调用。

同一 Tab 内多条线仍对齐到该 Tab 的 `dates`（长度一致）。**禁止**再为了 dates 去读美债 CSV，除非该 Tab 本身要展示美债。

### R2 对比页按 indicators 按需拉

`GET /api/macro/data/comparison?indicators=dxy,us_10y,vix,gold`

- `indicators` 必填，逗号分隔，白名单为对比模块现有 `IndicatorId`
- 非法 id → 400
- 后端把 id 映射到 CSV 段，只读这些段，日期轴为所选序列并集
- 默认四个：`dxy, us_10y, vix, gold`（与 `DEFAULT_INDICATORS` 一致）
- 用户多选：用当前完整 id 列表再请求；若新列表是已缓存列表的子集，前端不重拉
- 最多 6 个（现有 `MAX_INDICATORS`）

`tab=comparison` 且不带 `indicators` → 400，禁止再走全量。

### R3 前端按 Tab 请求 + 内存缓存

- 当前 Tab 第一次进入才请求；切走再切回走内存
- TTL **5 分钟**；点该 Tab 的「更新」或 `refreshKey` 变化则清该 Tab 缓存再拉
- **去掉** `economic_tab_data_cache:` localStorage
- 对比页缓存 key = 排序后的 `indicators` 列表，不是整个 comparison Tab 一份全量
- 时间范围 1M/6M/ALL 仍在前端 `useFilteredEconomicData` 切片，不因切时间范围再请求

### R4 Loading

- 仅当前可见 Tab 的图表区域显示 loading：转圈 + 「加载{Tab名}数据中…」
- 顶栏 Tab 可点，不使用全屏 `LoadingOverlay`
- 首次进入、TTL 过期重拉、点更新、对比页因新指标重拉：都要有 loading
- 内存命中：不闪 loading

### R5 现有 Tab 行为不回退

中美利差 / 流动性 / 利率 / 商品 / 股指 / 市场情绪 / 对比：切 Tab 后曲线能画出来（有 CSV 的前提下）。利率图必须仍有美债 3M。宏观信号不变。

## 约束

- 不改 `POST /api/macro/update/*`、`POST /fetch/*/history`、调度 `scheduler.json`
- 不恢复德债日债 Tab
- 不把宏观信号并进 `/data/{tab}`
- `EconomicDataResponse` 字段名不变，只是单次响应里缺省其它 Tab 的字段
- 不引入新依赖

## 验收标准（Acceptance Criteria）

- [ ] **AC1** DevTools：切到中美利差只出现 `GET /api/macro/data/treasury-exchange`，没有无 tab 的 `/api/macro/data`。默认 Tab 是信号首页（`macro-signal`，由其它任务设定），首屏不打图表 `/data/{tab}`
- [ ] **AC2** 切到市场情绪只打 `/api/macro/data/market-sentiment`；响应含 `volume/turnover/margin` 和 `dates`，不含 `us_treasuries`；`dates` 来自这三条 CSV 的并集。本地仅 2 个交易日时，图上能看出这两天，而不是钉在 6 个月轴最右侧
- [ ] **AC3** 切到利率，响应含 `us_treasuries`（至少 3m）以及 dr007 / ted_spread / china_bond；美债 3M 曲线看得到
- [ ] **AC4** 切到对比，请求带 `indicators=`（默认四指标）；响应只有这些指标对应的字段。再勾选一个新指标会再请求，loading 出现在对比内容区；去掉已选指标不发请求
- [ ] **AC5** 切走再切回同一 Tab（5 分钟内、未点更新）不再发网络请求
- [ ] **AC6** 首次进入某 Tab 或点更新时，该 Tab 内容区有转圈 loading，顶栏仍可切换
- [ ] **AC7** 无 `{tab}` 的 `GET /api/macro/data` 仍返回全量（调试用）
- [ ] **AC8** `GET /api/macro/data/macro-signal`、`GET /api/macro/data/bonds`、`GET /api/macro/data/comparison`（无 indicators）均为 400
- [ ] **AC9** 后端单测覆盖：tab 字段裁剪、market-sentiment 日期轴不读美债、rates 含 us_treasuries、comparison 按 indicators 映射、非法 id/缺 indicators
- [ ] **AC10** 前端无 `economic_tab_data_cache` localStorage 写入

## 范围外

- 补市场情绪历史（仍靠盘后追加）
- gzip / Cache-Control 总包优化（已有任务做过）
- 调度与 update 端点

市场情绪图 `yaxis2.overlaying: 'y'` 已作为可见性阻塞项落地（换手率否则画不出来），不再另开任务。

## Notes

- 与进行中的 `08-25-macro-market-sentiment-tab` 分工：那个任务负责成交额/换手率/融资余额的写入与 Tab UI；本任务负责读数拆分、日期轴、对比按需、loading。本任务落地后市场情绪空图应能按 AC2 看见那几天的点。
- `GET /data/{tab}` 保持 `def`（非 async），与总包 `GET /data` 一样进线程池。

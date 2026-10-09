# Macro Daily Snapshot API Contract

> **Purpose**: 信号首页 · 日频区块的接口契约与跨层对齐约定。改动 3 维度指标清单、15:00 规则或回退语义前必读。
>
> **Last verified**: 2026-10-09
> 信号首页自 2026-08-31 起为单页双区块(月度 4 卡 + 日频 3 卡同屏,MacroSignalTab 挂载即并行请求,无模式切换/懒加载)
> 2026-09-01:日频 monetary_policy 组加 DR001(隔夜),与 DR007(7 天)并列展示。前端组标题日频模式显示「流动性」(月度模式仍为「货币政策」,后端 dimension key 仍为 `monetary_policy`,API 无变更)。详见 §2.1。
> 2026-09-15:修正 DR001 恒空 bug——`prr-md.json` 真实响应 `records` 在**顶层**(`data` 下仅 showDateCN/showDateEN),`extract_dr001` 此前按 `data.records` 解析导致自上线起解析永远失败、被失败隔离静默吞成 null;测试 mock 与代码同错,测试全绿但从未对过真实接口。详见 §2.1 响应结构小节。
> 2026-09-16:DR001 弃用 prr-md.json 实时旁路,改为 DR007 同款定时落库(`POST /update/dr001` → 同一 `prr-chrt.csv` 取 index 6 列 → `dr001.csv`),获得 asof 回退能力;prr-md 实时链路代码整体删除。详见 §2.1/§4。
> 2026-09-20(上午):修正 `POST /update/dr001`「数据已落库但响应报失败」问题——新增更新端点的载荷类型必须同步加入共享 `UpdateResponse.data` 联合类型，并以端点级测试覆盖成功响应。详见 §7。
> 2026-09-20:日频扩充至 **3 维度 13 指标**——exchange_rate 组追加北向资金 3 指标(`north_today_yi`/`north_7d_avg_yi`/`north_7d_change_pct`,7 日窗口口径见 §2.2),risk_appetite 组追加南向净流入(`south_net_yi`);4 个新 key 均挂 `INDICATOR_LINK_MAP → market-sentiment` 曲线跳转。北向净买额自 2024-08 停发,只能上成交额口径。详见 §2.2/§5。
> 2026-09-20(第二批):monetary_policy 组追加中债利率 2 指标——`cn_10y`(列「中国10y」)/`cn_10y_2y`(列「中国10年-2年」),数据源 `load_data:china_bond`(china_bond.csv),单点 asof;2 个 key 挂 `INDICATOR_LINK_MAP → rates` 曲线跳转(该 Tab 数据段含 china_bond)。日频扩充至 **3 维度 15 指标**。详见 §2.3/§5。
> 2026-09-20(第三批):exchange_rate 组追加 `cn_us_10y_spread`(中美利差,派生序列见 §2.4)与 `vix`(vix.csv `Close_VIX` 列);前者跳转 treasury-exchange、后者跳转 liquidity-risk。日频扩充至 **3 维度 17 指标**。本地环境 vix.csv 缺失属正常——`/update/vix` 由 scheduler 北京早晨批量 job 触发,未跑过则 value=null。详见 §2.4/§5。
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

### 2.2 北向/南向资金指标(2026-09-20 引入)

- 数据源:`load_data:fund_flow` 读 `fund_flow.csv`(列 `date,北向成交额,南向净流入,南向买入,南向卖出`),由 `fund_flow_service.py`(akshare stock_hsgt_hist_em)每日更新。
- **北向只有成交额口径**:净买额(BUY_AMT/SELL_AMT/NET_DEAL_AMT)自 2024-08-16 起交易所停发,不要再尝试净流入口径。
- 三个 key:`north_today_yi`(当日成交额,单点 asof)、`north_7d_avg_yi`(含当日最近 7 个交易日窗口均值)、`north_7d_change_pct`(当前窗口日均 vs 前一窗口日均的百分比变化)。窗口计算在 `daily_snapshot_service.py::_extract_windowed`,基于序列自身交易日(asof ≤ 所选日期);窗口不足 7 日 → value=None 但保留 data_date。
- `south_net_yi`(南向净流入,亿港元)归 risk_appetite 组:南向是内地资金外溢信号,非外部压力;无评分体系引用,纯数据展示。
- 窗口指标 `prev_value` 恒 None:均值类指标的日变化无意义,环比已有专门 key。前端对 prev_value=None 自动不渲染日变化箭头。
- 4 个新 key 均有 `INDICATOR_LINK_MAP → market-sentiment` 曲线跳转(该 Tab 含 fund_flow 曲线)。
- 与 exchange-rate-skill 月度评分体系的中文 key(`北向7日日均成交额` 等)是不同 key 空间,`INDICATOR_LABELS` 独立条目、digits 不同(日频环比 1 位、skill 中文 key 2 位),互不覆盖。

### 2.3 中债利率指标(2026-09-20 引入)

- 数据源:`load_data:china_bond` 读 `china_bond.csv`(表头 `date,中国10y,中国10年-2年`),单点 asof,与 exchange_rate 组单点指标同款语义(value/prev_value/data_date 完整)。
- 两个 key:`cn_10y`(中债 10Y 到期收益率,列「中国10y」)、`cn_10y_2y`(中国 10Y-2Y 期限利差,列「中国10年-2年」),单位 %、digits 2。
- 2 个 key 均挂 `INDICATOR_LINK_MAP → rates` 曲线跳转(rates Tab 数据段含 china_bond,`RatesChart.tsx` 渲染该曲线);`data_service.py` 另有同名 key 映射到 `china_bond`(query_data_by_tab 用),与本清单互不影响。
- 归 monetary_policy 组(日频标题「流动性」),组内仍不渲染档位刻度。

### 2.4 中美利差与 VIX(2026-09-20 引入)

- `cn_us_10y_spread` = 中国10y − 美债10y(正=中国利率更高,负=倒挂)。**派生序列**:两个 CSV 无交集日期保证,`_load_cn_us_10y_spread` 以中国交易日轴为基准,美债10y `reindex(ffill)` 对齐后做差(美国节假日缺日由 ffill 兜底)。`_DAILY_INDICATORS` 条目用 `derived:` 前缀 loader 表达,`_load_series` 分派到同名 `_load_*` 方法;派生序列复用 `_extract` 的 asof/prev_value 语义。
- treasury-exchange Tab 实际是「美债+中国10y 双曲线对比」展示,无独立利差序列——前后端口径独立,`INDICATOR_LINK_MAP` 指向该 Tab 仅为就近看两条源曲线。
- `vix` 读 vix.csv `Close_VIX` 列(`_save_vix` 写入,FRED VIXCLS 源)。更新链路:scheduler 北京早晨批量 job(`美债/汇率/VIX/TGA/HIBOR/TED/商品/指数` 顺序)→ `/update/vix`。**环境未跑过该 job 时 vix.csv 不存在,value=null 属正常**,接口不报错。
- 2 个 key 跳转:`cn_us_10y_spread → treasury-exchange`,`vix → liquidity-risk`。

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
- CSV 数值列是中文列名(如 `美元指数`/`TED利差`/`北向成交额`),与英文 key 的映射只存在于 `_DAILY_INDICATORS`
- 当前各组 key 清单(2026-09-20,17 指标):
  - `monetary_policy`:`dr001`、`dr007`(`INDICATOR_LINK_MAP` 无条目,无曲线跳转)、`cn_10y`、`cn_10y_2y`(均 → `rates`)
  - `exchange_rate`:`dollar_index`、`usd_cny`、`ted_spread`、`hibor_overnight`、`north_today_yi`、`north_7d_avg_yi`、`north_7d_change_pct`、`cn_us_10y_spread`(→`treasury-exchange`)、`vix`(→`liquidity-risk`)
  - `risk_appetite`:`volume`、`turnover`、`margin`、`south_net_yi`

## 6. dates 列表口径

`volume` 序列(A股交易日,每交易日必有值)近 60 个 ∪ 今日。以 volume 为交易日基准的原因:三张卡中 DR007/市场情绪均为 A股日历;美元/TED 指标在非美交易日的缺失由行级 asof 回退兜底。

## 7. 更新端点注册表与共享管道契约（2026-10-09）

### 1. Scope / Trigger

新增或修改任何返回 `UpdateResponse` 的 `/api/update*` 端点，或修改 fetch / validate / save / payload 阶段时适用。

### 2. Signatures / Files

- `update_pipeline.py::UpdatePipeline.execute(spec: UpdateSpec, context: UpdateContext) -> UpdateResponse` 是路由唯一执行入口，统一锁、成功/失败响应和 no-op 处理。
- `UpdatePipeline.run_stages(UpdateStages)` 执行 `fetch → validate → save → build_payload`；`run(...)` 保留为四阶段通用执行器。
- `update_registry.py::UPDATE_SPECS` 的 18 条 `UpdateSpec` 必须登记 key、endpoint、payload_type、contract_test_file、**可执行** `build_stages`、success_message、failure_message。
- `update_sources/{fred,a_share,cross_source,final,market}.py` 按域声明 `build_*(context) -> UpdatePlan`。`UpdatePlan` 包含四阶段回调和可选 `on_no_data` 回调；阶段构造器不能自行落库。
- `routes.py::_update_context()` 显式注入服务工厂、共享取数/增量辅助函数和锁回调。工厂必须惰性调用，构造 context 不打开无关源。服务层不得反向 import API。
- 18 个更新路由仅保留说明和 `return await UpdatePipeline.execute(UPDATE_SPECS[key], _update_context())`，目前平均 3.6 行、最大 5 行（含签名/说明）。

### 3. Contracts

- 历史回补路由与更新管道共用同一个 `_is_updating` 状态。锁被占用时不调用阶段构造器、不释放其他请求的锁；成功、失败、no-op 和取消执行均在持锁执行的 `finally` 中释放锁。
- 校验失败必须发生在 save 前。`NoNewData` 仅供该源已有空窗语义使用，由 `UpdatePlan.on_no_data` 保留原成功响应；准备阶段发现已是最新则抛 `UpdateNoOp(response)`，不会 fetch/save。
- 保留响应字段、消息、HTTP 200、`UPDATE_IN_PROGRESS` / `UPDATE_FAILED` 语义，存储方法与 CSV 路径不变。
- `/update` 保留兼容入口：注册 `legacy` 的组合阶段依次获取美债、OECD、汇率，在同一次持锁管道内保存并构造 `MacroDataWithRates`；不能循环调用其他 HTTP 包装器导致锁重入。
- `UpdateResponse.data` 继续使用显式联合类型。测试双向检查所有增量载荷必须有登记；额外仅允许两个历史回补载荷（`VolumeTurnoverHistoryUpdateData` / `MarginHistoryUpdateData`）和两个保留的旧公共 schema（`MacroData` / `MacroDataWithRatesAndVIX`）。例外固定列出理由，不因新增类型而自动放宽。
- 注册表 key/path 不重复，路径集合与实际 18 条增量路由相同。每个源必须有成功与失败 HTTP 契约，使用 `pytest.mark.update_contract(key, outcome)` 在实际参数用例上登记；只检查文件存在不够。

### 4. Validation & Error Matrix

| 条件 | 预期结果 |
|---|---|
| fetch 抛异常或 validate 失败 | 不执行 save，返回既有 `UPDATE_FAILED` 语义 |
| 增量窗口无观测且符合该源已有 no-op 规则 | 保留 `success=true` / “已是最新” 响应，不落库 |
| payload 漏入 `UpdateResponse.data` | 正向联合类型测试失败 |
| 注册条目删除/新增未登记的联合类型 | 反向联合类型或路由集合测试失败 |
| 文件保留但对应参数用例删除 | pytest 实际 collection 的成功/失败覆盖检查失败 |
| 注册项存在但路由绕过它 | 替换该项构造器的 HTTP 测试失败 |

### 5. Adding a Source

1. 定义 payload 并加入 `UpdateResponse.data`。
2. 在对应域声明 `build_*(context) -> UpdatePlan`，复用已有 DataService 保存方法。
3. 将可执行构造器、路径、载荷类型、测试文件及响应消息登记到 `UPDATE_SPECS`。
4. 添加薄路由包装器；添加成功/失败 HTTP 用例，并在**对应参数项**标记 `update_contract(key, "success"/"failure")`。
5. 运行契约、完整性和全套测试，再根据产品要求另行决定是否加入 scheduler；欧债/日债排班仍不在本任务范围。

### 6. Tests Required / Evidence

- `tests/test_update_contracts_*.py`：18 个端点成功载荷与保存调用、失败不落库；`test_incremental_empty.py` 保留空窗/底库过期语义。
- `tests/test_update_pipeline.py`：每项可执行、每条 HTTP 路由实际调用其注册构造器且失败释放锁、路径唯一与四阶段顺序。
- `tests/test_update_registry.py`：联合类型双向校验；在子进程实际收集契约参数项，逐源验证成功/失败覆盖。自动变异验证删除任一注册项、漏任一联合类型成员、删除单个契约用例均能拦截。
- `tests/test_update_integration.py`：18 个端点使用真实 DataService 写隔离 CSV；完整成功响应对照 `fixtures/update_success_responses.json`。fixture 来源于迁移前提交 `23ffeba`，只归一化请求时间和变化的日历日期。
- 同一集成测试手动调用真实 `SchedulerManager._run_job_wrapper`，两组经 ASGI HTTP 调用实际端点，检查真实 CSV 日期与 JSONL 执行历史；**仅外部数据源替换为夹具**，无 NAS/真实第三方源可用性结论。
- 2026-10-09 全套 `python -m pytest tests/ -q`：394 passed；Ruff F 检查和新模块 I 检查通过。浏览器现有“中美利差/汇率”刷新按钮串行三个 POST 成功、重载数据并记录成功时间；前端未改动。

### 7. Wrong vs Correct

```python
# Wrong: registry is only metadata, while routes own their stage callbacks.
async def update_foo():
    data = await fetcher()
    save(data)
    return UpdateResponse(data=FooUpdateData(...))

# Correct: a registered source prepares all four stages; the shared executor
# owns locks/errors/no-op responses and runs the same flow for every endpoint.
async def update_foo():
    return await UpdatePipeline.execute(UPDATE_SPECS["foo"], _update_context())
```

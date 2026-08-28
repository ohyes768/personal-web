# 执行计划:宏观信号首页 + 日频快照

> 按序执行;每步末尾的验证命令通过后再进入下一步。
> 后端验证:`cd backend/macro && ./.venv/bin/python -m pytest tests/ -v`(Windows dev 用对应 venv 激活方式)
> 前端验证:`cd apps/macro && pnpm lint && pnpm build`
>
> **执行记录(2026-08-28)**:全部完成。
> - `pnpm lint` 实际不可用:项目无 ESLint 配置,`next lint` 触发交互式初始化(预存状态),类型检查由 `pnpm build` 覆盖
> - 后端全量 pytest:106 passed + 1 个预存失败(`test_get_data_comparison_without_indicators_is_400`,stash 改动前同样失败,与本次无关)
> - 手测(Chrome,后端假 FRED key + 本地 data/):15:00 规则、回退标注、日期步进(跳过非交易日)、双模式状态保持、红涨绿跌、显式日期取值、非法日期 400 全部通过

## Step 1:后端 models + daily_snapshot_service

- [ ] `models.py`:`DailyIndicator` / `DailyGroup` / `DailySnapshotData` / `DailySnapshotResponse`
- [ ] 新建 `services/daily_snapshot_service.py`:
  - `_resolve_default_date()`:15:00 规则(volume 序列最大可用日期)
  - `get_daily_snapshot(date: str | None)`:45 天窗口拉 rates / treasury-exchange / market-sentiment 三个 tab,按列 asof 取 value/prev_value/data_date,组装 groups + dates
  - 指标映射:`dr007→dr007`,`exchange_rates.dollar_index→dollar_index`,`exchange_rates.usd_cny→usd_cny`,`ted_spread.ted_spread→ted_spread`,`volume/turnover/margin` 同名
- [ ] 单测 `tests/test_daily_snapshot.py`:默认日期 15:00 前后两分支、显式 date 取值正确、无值日期回退+data_date 标注、dates 列表长度与降序、非法 date 400

验证:`python -m pytest tests/test_daily_snapshot.py -v`

## Step 2:后端路由

- [ ] `routes.py` 新增 `GET /daily-snapshot`(同步 `def`,复用 `/data` 的线程池理由注释),参数 `date: Optional[str]`
- [ ] 手测:`curl "http://localhost:8094/api/daily-snapshot"` 与 `?date=2026-08-27`,核对 JSON 结构

验证:`python -m pytest tests/ -v`(全量,防回归)

## Step 3:前端类型 + 常量

- [ ] `lib/modules/macro-signal/types.ts`:新增 `DailyIndicator` / `DailyGroup` / `DailySnapshot` 类型(对齐后端契约)
- [ ] `constants.ts`:新增 `DAILY_GROUPS`;`INDICATOR_LABELS` 补 `volume` / `turnover` / `margin` 英文 key;`INDICATOR_LINK_MAP` 补 `dr007` / `volume` / `turnover` / `margin`

验证:`pnpm lint`

## Step 4:日频组件

- [ ] `DailySwitcher.tsx`:◀/下拉/▶,dates 数组内步进,两端禁用
- [ ] `DailyCardGrid.tsx`:3 卡网格 + 指标行(label / value / ▲▼变化 / 回退日期标注 / 📈 跳转)

验证:`pnpm lint && pnpm build`

## Step 5:MacroSignalTab 改造

- [ ] 新增 `mode` 状态 + 顶部「月度/日频」分段切换器(胶囊按钮,选中态高亮)
- [ ] monthly 分支:默认月份改「上个月」,availableMonths 就绪后按回退规则校正;现有 6 卡渲染不动
- [ ] daily 分支:`selectedDate` 为 null 时首拉不带 date,采纳响应 `date` 与 `dates`;手动切换后显式传 date;loading/error 态与月度分支同款骨架/错误样式

验证:`pnpm build`;`pnpm dev` 手测双模式切换、状态保持

## Step 6:page.tsx 置首

- [ ] tabs 数组 `macro-signal` → index 0,label「信号首页」
- [ ] `activeTab` 初始值 `'macro-signal'`

验证:`pnpm build` + 浏览器进 `/macro` 默认落首页 Tab

## Step 7:全量校验(2.2 最后迭代)

- [ ] 后端:`python -m pytest tests/ -v` 全绿
- [ ] 前端:`pnpm lint && pnpm build`
- [ ] 手测清单(对照 prd.md Acceptance Criteria 逐条):
  - 默认 Tab 与 Tab 顺序
  - 月度默认上个月、切月正常
  - 双模式切换状态保持
  - 15:00 规则(可临时改本机时间或 mock 验证逻辑单元性)
  - 7 项指标与曲线 Tab 最新值一致
  - 回退标注、日期切换器边界禁用

## 回滚点

- 每个 Step 独立可编译:Step 1-2 纯新增(不调用即无影响);Step 3-4 新文件;Step 5-6 为唯一改动现有文件的两步,git checkout 对应文件即回滚

## Review Gate

- Step 2 完成后:后端契约 review(响应结构 vs design.md §2)
- Step 5 完成后:前端交互 review(对照 prd.md R2-R4)

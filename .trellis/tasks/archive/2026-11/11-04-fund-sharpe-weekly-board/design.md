# 夏普榜单技术设计

## 架构与取舍

采用现有股基周刷新 + 结构化周榜批次/观测表 + 独立只读页面。两个来源分开记录，Tab 内切换。不另起全市场采集，不从当前指标反推历史，不改旧筛选表格。

仅写日志难以保证唯一和聚合；仅存曲线点无法表达成功空榜或失败，所以同时保存批次和观测。

## 固定规则和周标识

新增 `src/services/sharpe_board_service.py`，定义 stock:v1、discovery-stock:v1 两套 profile，字段为 source/version/filters/collection_prefilters/algorithm_version，条件见 PRD。市场使用 DISCOVERY_STOCK_SUBTYPES 确定副本；canonical JSON/hash 随榜保存。

记录参数 min_sharpe 和展示参数 min_latest_sharpe 分开。规则变化新建 v2，不改旧周规则。week_start 为 started_at 转 Asia/Shanghai 后所在周周一，跨周完成仍归开始周；显示实际日期，tooltip 显示实际执行时间。

## 新表

在 `backend/fund-select/src/db/models.py` 新增，现有 create_all 初始化。

**SharpeBoardWeek / sharpe_board_weeks**：id PK；source/profile_version/week_start 联合唯一；profile_json/profile_hash/algorithm_version；status=complete|failed|skipped_no_new_data；run_id/trigger/started_at/finished_at/published_at；selected_count/errors_json/diagnostics_json。时间保存 UTC，展示北京时间。running 复用 scheduler 当前状态。complete 后不可重写，failed/skipped 可同周重试；每次尝试仍保留现有 JSONL 审计。

**SharpeBoardObservation / sharpe_board_observations**：week_id+code 联合唯一，week_id 外键；name 为入选时名称快照，sharpe 为有限数；metric_calculated_at/returns_end_date/sample_days；evidence_json 保存筛选字段和来源刷新 ID。不引用实时 Fund 作删除级联，避免当前清盘/改名抹掉历史。

NULL/NaN/Infinity、无本轮证据的指标不写观测。原子事务发布批次和全部观测，失败 rollback，唯一冲突时保留首个 complete。

## 本轮采集与发布

新增 `src/services/sharpe_capture.py`，只在两个股基 weekly wrapper 中启用可选 capture，旧调用默认 None：

```python
@dataclass
class SharpeRunCapture:
    run_id: str
    base_rows: dict[str, dict] = field(default_factory=dict)
    risk_rows: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
```

1. `refresh_tab_sync` 创建 capture，透传 stock collector/market stock pipeline/risk service；采集函数本轮成功 commit 后冻结筛选字段、universe、风险值及实际样本尾日。发布不重新读可能被普通刷新覆盖的最新行。
2. `MetricsResult` 增加默认 None 的 returns_end_date，来自计算夏普的 joined 样本；保留原位置参数兼容，公式不改。网络失败与有效但样本不足分开诊断；当前 _safe_fetch_nav 吞异常返回空表，capture 路径需额外保留失败证据。
3. 固定规则筛选冻结数据。将现有 FilterService 的入选谓词提取成可复用的小函数，实时查询和 capture 共用；用旧筛选测试保证阈值、负回撤、NULL、市场子类语义等价，不复制独立逻辑。按代码去重，不受 API 页长限制。
4. stock 基准/风险错误和 market 阶段错误均汇入 capture；有输入采集错误则本轮不发布完整榜，记 failed。有效但无指标记诊断和不入选，正常零命中发布 complete 空榜。
5. 样本尾日相对该来源上次发布无更新的基金不写新点并计 diagnostics；所有风险样本无新增则 skipped_no_new_data。个别数据未更新的断点须标数据状态，不能称为确定不达标。
6. scheduled/manual 调度均可发布当前周，普通页刷新不发布；成功本周冻结，失败可重试。发布失败独立 snapshot_status=failed，不抹掉采集结果、不阻断队列后续任务。债基不接 capture。

首次上线不回算、不倒填；遗漏过往周只留横轴空位。新表发布 hook 可独立撤下回退。

## API 与统计合同

新增 `src/api/sharpe_board.py` 路由及 DTO，main.py 在通用详情 router 之前注册。

```text
GET /api/funds/sharpe-board
source=stock|discovery-stock（默认后者）
profile_version=v1
min_latest_sharpe=可空有限数[-10,10]
min_weeks=整数>=1（默认1）
latest_only=false
range=3m|6m|1y|all（默认all）
page>=1，limit=1..200（默认50）
```

非法参数 422，未知版本 404。返回 profile、latest_published_week、latest_attempt、stale、total、items、weeks、series、diagnostics。未知状态字段不能被 Pydantic 静默截掉。

- items 每条含 code/name/listed_weeks/consecutive_weeks/latest_sharpe/last_listed_week/on_latest_board。
- 先在当前 source/version 的 complete 全历史聚合，按 latest_sharpe、listed_weeks、latest_only 筛选，再按 `(listed_weeks DESC, latest_sharpe DESC, code ASC)` 排序和分页。
- latest_only 用当前来源最新 complete 周榜，不用各基金最后一次记录周；最新 complete 空榜时返回零只。若当周失败/停机，要显示旧榜日期和 stale，不冒充本周。
- weeks 为所选范围内从首次观测到当前自然周的统一周历，成功空榜、失败、停机及缺席均留位置。
- series 为全部命中基金，不随 items 分页：`{code,name,values:[number|null]}`，长度等于 weeks。range 只裁图，不改全历史统计；范围内无点时保留列表并提示，图不造点。
- 连续周从各基金最近上榜周向前数相邻自然周，缺席/未知均中断，列名说明为最近一段连续周数。
- 不 JOIN 当前 is_active 过滤历史。数据量预算 300 只×104 周，不静默截 top N。

## 前端设计

路由源文件 `apps/fund-select/src/app/sharpe-board/page.tsx`，访问 /funds/sharpe-board。提取 `FundsNavigation.tsx` 供旧 FundsHeader 和新页面复用；旧 FundsTab/exportKind 仍只代表四种刷新来源，不伪造 filters/onRefreshed 给新页面。新页面可复用 SchedulerDialog。

顶部来源切换 + 入选规则只读说明 + 最新榜日期/采集状态；展示筛选；总图；分页列表。新 `lib/sharpe-board.ts` 独立 DTO/URL 参数/请求，fetch 完整 /funds/api/funds 前缀，AbortController 防旧响应覆盖新来源。

应用内安装 echarts ^6.0.0，仅新页动态加载，Canvas 折线；`connectNulls:false`、`smooth:false`、单点显示 symbol，纵轴不强制从零开始；滚动图例、dataZoom、tooltip、夏普下限参考线。全部命中默认可见，图例隐藏/列表聚焦/恢复全部；低于展示下限的历史点仍保留。

`lib/sharpe-chart.ts` 纯 option 构造，与 `components/sharpe-board/SharpeChart.tsx` 生命周期分开。ResizeObserver，隐藏容器不 init，卸载 dispose。数值表格提供颜色之外的信息。

明确区分首次无数据、采集失败、成功空榜、展示无匹配、时间范围内无点。390px 筛选换行，表格局部滚动，无页面横向溢出。已有通用 Next 代理无需改。

## 验证与回退

后端覆盖唯一/事务/全量采集/冻结输入/空榜失败区分/边界周/聚合。前端验证纯 option 与 URL 逻辑、tsc、构建、1440px/390px 浏览器。合成 300×104 数据记录首图耗时，目标普通桌面不超过 2 秒，超预算优化而非删基金。

回退移除发布 hook 和导航入口，保留新表，不删除旧业务数据。图表依赖和锁文件一起改；Windows standalone 若遇 symlink 权限限制记录真实错误，不能宣称构建成功。

# 基金夏普榜单 Implementation Plan

**Goal:** 独立 Tab 展示每周入选记录，按累计在榜周数排序，以最近上榜夏普筛选完整历史曲线。

**Architecture:** 两条现有股基周采集捕获本轮冻结输入，完成后原子发布带规则版本的榜单；只读 API 聚合；Next 独立页面通过现有代理读取。

**Tech Stack:** FastAPI、SQLAlchemy、SQLite、pytest；Next 15、React 19、TypeScript、ECharts 6。

**执行边界：** 本文件是执行规划，所有步骤未执行。实施需后续用户指令，再用 trellis-before-dev 加载最新规范、核对其他工作区改动，按当时 Trellis 平台路由进入执行；不因本文件默认派发子代理。用户未授权时不提交或部署。

## 步骤 1：模型、规则与周标识（AC5、AC7、AC8）

文件：修改 `backend/fund-select/src/db/models.py`；新增 `backend/fund-select/src/services/sharpe_board_service.py`、`backend/fund-select/tests/test_sharpe_board_service.py`。

- [ ] 先写唯一约束与隔离测试：同 source/version/week 两行失败，不同 source/version 可共存；使用 tmp_path 文件 SQLite 验证重新开连接仍保留。
- [ ] 按 design 建两表及索引，复用 create_all，不修改旧表。
- [ ] 定义 PRD 两套 profile 和 canonical JSON/hash。规则变更必须换 version，数据记录完整规则副本。
- [ ] 实现周键函数并测试跨年/跨周：

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def recording_week(started_at: datetime):
    if started_at.tzinfo is None:
        raise ValueError("started_at must be timezone-aware")
    local = started_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
    return local - timedelta(days=local.weekday())

def test_recording_week_cross_year():
    started = datetime.fromisoformat("2027-01-01T10:05:00+08:00")
    assert recording_week(started).isoformat() == "2026-12-28"
```

- [ ] 用 complete 零入选、failed、skipped_no_new_data 三种 fixture 验证状态区分；complete 的同周重试不覆盖。

运行（cwd `backend/fund-select`）：

```powershell
python -m pytest tests/test_sharpe_board_service.py -q
```

先确认测试因缺模型/函数失败，最小实现后全部通过。

## 步骤 2：冻结本轮输入与风险日期（AC2、AC6、AC7）

新增 `backend/fund-select/src/services/sharpe_capture.py`、`tests/test_sharpe_board_capture.py`；修改同包 `src/scheduler/tasks.py`、`src/services/market_full_pipeline.py`、`market_risk_refresh.py`、`risk_service.py`；扩展 `tests/test_risk_refresh.py`。

- [ ] 测试 A 本轮成功、B 网络失败但库里有旧高夏普：capture 必须标失败，不能用旧 B 发布。
- [ ] 为两股基 collector/pipeline/risk 函数加可选 capture=None 参数；旧路径默认行为和返回字段兼容。
- [ ] commit 后冻结本轮基础字段、名单/精确子类、风险值。采集异常保留到 capture.errors；有效但指标无定义单独记诊断，不能把 _safe_fetch_nav 吞掉的网络异常当正常缺值。
- [ ] MetricsResult 添加默认 None 的 returns_end_date，由计算夏普所用 joined 索引最大日期产生，保留现有位置参数构造兼容，不改计算公式。
- [ ] 对共享最新表被另一次普通刷新覆盖写测试：capture 的字段和风险仍来自本轮。
- [ ] 将入选谓词提取给实时 FilterService 与冻结数据共用；用旧查询结果作等价测试，覆盖负回撤、等号、NULL、QDII、精确 subtype。筛选条件与 market 采集预筛一起保存。

```powershell
python -m pytest tests/test_sharpe_board_capture.py tests/test_risk_refresh.py tests/test_risk_service.py tests/test_stock_filter_service.py tests/test_discovery_filter_service.py -q
```

预期新测试与原风险/筛选回归全通过，旧 capture=None 路径结果不变。

## 步骤 3：原子发布并接每周任务（AC5、AC6、AC8、AC10）

修改 `backend/fund-select/src/services/sharpe_board_service.py`、`src/scheduler/weekly_refresh.py`；扩展 `tests/test_sharpe_board_service.py`、`tests/test_weekly_refresh.py`。

- [ ] 先写 202 只入选基金测试，确保全量输入均记录且 code 去重；一次事务写批次/观测，中途失败全 rollback。
- [ ] 实现首次 complete 冻结；同周重复不计次，failed/skipped 可同周成功重试。并发唯一冲突返回已有 complete。
- [ ] 测试 stock 原 returned failed 没覆盖的风险错误和 market L4 错误，均不会误发完整榜。
- [ ] 比对 capture 样本尾日与最近榜；个别无新增样本不写点并计诊断，全部无新增为 skipped；有效全量输入零入选则发布 complete 空榜。
- [ ] 仅给 stock/discovery-stock 的 refresh_tab_sync 接 capture 和发布；scheduled/manual 当前周生效，原页面普通刷新不发布，债基不接入。
- [ ] 发布失败报告 snapshot_status，保留 collector 成功结果和旧榜，不阻断后续任务；recording_week 用 started_at，不用 finished_at。

```powershell
python -m pytest tests/test_sharpe_board_service.py tests/test_sharpe_board_capture.py tests/test_weekly_refresh.py tests/test_scheduler_management.py -q
```

预期：同周只一榜、零榜/失败可区分、四项 cron 和队列行为回归通过。不运行真实全市场采集。

## 步骤 4：聚合服务与 API（AC2–AC8、AC10）

新增 `backend/fund-select/src/api/sharpe_board.py`、`tests/test_sharpe_board_api.py`；修改 `src/services/sharpe_board_service.py`、`src/api/models.py`、`src/main.py`。

- [ ] 建三周 fixture：周一 2026-10-19/10-26/11-02；A=[0.95,None,1.05]，B=[0.90,0.92,0.94]。断言无筛选时 B(3周)在 A(2周)前；A 最近连续1周、B连续3周。
- [ ] 实现 design 的全历史聚合、展示筛选、排序后分页；series 包含全部命中基金。
- [ ] API 测试核心断言采用以下固定值，不仅检查 HTTP 200：

```python
body = client.get("/api/funds/sharpe-board", params={
    "source": "stock", "profile_version": "v1", "min_latest_sharpe": 1,
}).json()
assert body["total"] == 1
assert body["items"][0]["code"] == "000001"
assert body["items"][0]["listed_weeks"] == 2
assert body["series"][0]["values"] == [0.95, None, 1.05]
```

- [ ] 测 min_weeks=3 只剩 B；range 改末周不改累计/最新值；下限判断使用范围外最新记录；无范围内点不造点。
- [ ] 测最新 complete 是空榜时 latest_only 返回空；最新尝试失败时旧榜日期/stale/错误真实；周轴有停机空位。
- [ ] 注册静态 router 在通用详情路由前，Pydantic 明确 DTO 含 series/diagnostics；非法参数 422，未知版本 404。
- [ ] 失活基金历史仍在；两来源/版本隔离；items 分页和 series 全量、total 语义正确。

```powershell
python -m pytest tests/test_sharpe_board_service.py tests/test_sharpe_board_api.py tests/test_api.py -q
```

预期新 API 精确数值断言和旧 API 回归通过。

## 步骤 5：独立 Tab 和图表（AC1、AC3、AC4、AC9、AC10）

文件均位于 `apps/fund-select`：新增 `src/components/FundsNavigation.tsx`、`src/app/sharpe-board/page.tsx`、`layout.tsx`；新增 `src/components/sharpe-board/SharpeChart.tsx`、`SharpeBoardFilters.tsx`、`SharpeBoardTable.tsx`；新增 `src/lib/sharpe-board.ts`、`sharpe-chart.ts`、`sharpe-board.test.ts`、`sharpe-chart.test.ts`；修改 `FundsHeader.tsx`、`package.json` 及实际锁文件。

- [ ] 提取五 Tab 公共导航，旧 exportKind 只含四个采集来源；旧页除导航外无功能变化。
- [ ] 用项目实际包管理器安装 echarts ^6.0.0；仅新页动态加载，不跨应用 import。
- [ ] 定义独立 URL 参数/DTO/请求，source 改变时中止旧请求；筛选重置列表页，翻页不重置图状态。
- [ ] 新页面显示规则、来源、最新榜周和诊断，接展示筛选及表格；字段叫“最近上榜夏普”，不冒称“当前夏普”。
- [ ] 纯 option 测试校验完整数据、断线、单点、下限线：

```typescript
const option = buildSharpeChartOption({
  weeks: ['2026-10-19', '2026-10-26', '2026-11-02'],
  series: [{code: '000001', name: 'A', values: [0.95, null, 1.05]}],
  minLatestSharpe: 1,
});
assert.deepEqual(option.series[0].data, [0.95, null, 1.05]);
assert.equal(option.series[0].connectNulls, false);
assert.equal(option.series[0].smooth, false);
```

- [ ] 封装 Canvas 图生命周期，ResizeObserver/dispose/隐藏容器；滚动图例、tooltip、dataZoom、列表聚焦和恢复全部；保留全部命中，不能只取列表页。
- [ ] 明确首次空态、失败、成功空榜、无匹配、范围内无点；390px 表格局部滚动。复用 SchedulerDialog 补本周入口，展示筛选不触发采集。

运行（cwd `apps/fund-select`，Node 需支持 experimental-strip-types；纯测试文件使用可直接执行的相对 import）：

```powershell
node --experimental-strip-types --test src/lib/sharpe-board.test.ts src/lib/sharpe-chart.test.ts
npx tsc --noEmit
npm run build
```

预期：纯逻辑和类型检查通过；构建如遇 Windows symlink 限制记录实际输出及替代预览证据，不虚报通过。现有 next lint 未配置无交互运行，不能算已通过。

## 步骤 6：集成验证与规范（全部 AC）

更新 `.trellis/spec/backend/fund-select/backend/contracts.md`；新增 `.trellis/spec/frontend/fund-sharpe-board.md` 并从 frontend/index.md 链接；浏览器截图放本地忽略目录。

- [ ] 后端临时库/mock 数据跑全回归（cwd backend/fund-select）：`python -m pytest -q`、`python -m ruff check src tests`。
- [ ] 1440px/390px 浏览器核验五 Tab 导航和旧四页筛选/刷新/齿轮；榜单排序、下限保留低点、分页不裁图。
- [ ] 覆盖初次无历史、失败/重试、空榜、单点、断周、范围无点、全隐藏、来源快速切换、键盘和 tooltip，截图留证。
- [ ] 300 只×104 周 fixture 测全图渲染与图例，记录环境和耗时，目标普通桌面初始化 ≤2 秒；超预算优化查询/option/tooltip，不静默截基金。
- [ ] 逐项填写 AC1–AC10 的实际证据，执行 Trellis check，必要时修正后重跑相关检查；用户未要求时不提交、推送或部署。

## 风险与回退

最大风险是冻结输入透传与筛选等价，必须保住 capture=None 回归和原公式。分页、JOIN 重复、旧风险行误用会污染次数，需数值测试。日期不能从 as_of_date 伪造。

回退撤发布 hook 和新导航，保留新表，不删除旧表或已发布历史。

## 自检

R1–R9 均有步骤和 AC 映射。所有步骤未执行，无实现测试通过声明；用户当前授权仅为创建任务及规划，任务维持 planning。

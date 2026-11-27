# 技术设计：创业板50 纳入 index-trends

## 1. 边界

现有服务有一条隐式契约：**一个进程、一个指数、一套表**。本任务把这条契约改成「指数是一等公民」，但**不重写算法层**——通道拟合、周线模型、交易日历全部原样复用，只把"哪个指数"从常量变成参数。

改动集中三层：

| 层 | 文件 | 动作 |
|---|---|---|
| 指数注册 | `src/core/indexes.py`（新） | 定义 000300 / 399673 的 code、symbol、name、起始周、起始月 |
| 存储 | `src/services/store.py` | 6 张表加 `index_code` 维度；新增分位历史表；迁移 `006_multi_index` |
| 采集与编排 | `data/lixinger.py`、`services/*`、`api/routes.py`、`services/scheduler.py` | 全部按 index_code 参数化；估值加 metric 维度 |

算法层（`core/regression.py`、`core/weekly.py`、`core/weeks.py`）**零改动**。

## 2. 指数注册表

```python
# src/core/indexes.py
@dataclass(frozen=True)
class IndexDef:
    code: str            # "399673"
    symbol: str          # "sz399673"（腾讯 fqkline）
    name: str            # "创业板50"
    inception_month: str # "2014-06"
    inception_week: str  # "2014-06-16"（发布周周一）
    earliest_weekly: str # "2014-06-30" 周K必须覆盖到此日之前

INDEXES = (IndexDef("000300", "sh000300", "沪深300", "2005-04", "2005-04-04", "2005-04-30"),
           IndexDef("399673", "sz399673", "创业板50", "2014-06", "2014-06-16", "2014-06-30"))
BY_CODE = {i.code: i for i in INDEXES}
```

`trend_service.py` 的 `INDEX_CODE/SYMBOL/INDEX_NAME` 与 `core/models.INCEPTION_MONTH`、`WEEKLY_INCEPTION_WEEK`、`WEEKLY_REQUEST_COUNT` 的硬编码断言全部改为读注册表。`WEEKLY_REQUEST_COUNT` 保留 1600（覆盖 2014 至今绰绰有余）。

`fetch_and_validate` 里 `earliest > "2005-04-30"` 这条断言改为 `earliest > idx.earliest_weekly`——这是唯一会把 399673 拒掉的地方。

## 3. 存储改造（关键决策）

**方案 A（采用）：加 `index_code` 列 + 重建表。**

涉及表：`monthly_bars`、`daily_quotes`、`weekly_bars`、`data_meta`、`weekly_data_meta`。
`models` / `weekly_models` / `index_valuations` 已有 `index_code` 列，只需在读路径上加筛选。

迁移 `006_multi_index`：

1. 建新表（主键前置 `index_code`），从旧表 `INSERT INTO new SELECT '000300', * FROM old`；
2. `DROP` 旧表、`RENAME`；
3. 重建索引；
4. 全流程在单事务里完成，失败回滚（沿用 `schema_migrations` 现有机制）。

`data_meta` / `weekly_data_meta` 目前是 `id=1` 单行，改为主键 `index_code`，回填 `'000300'`。`valuation_fetch_meta` 同理改为 `(index_code, metric)` 主键——多指数才能各自记失败状态，否则一个指数的失败会污染另一个（PRD R2/R4）。

**为什么不用「每个指数一个 db 文件」**：改动小但把"多指数"藏进文件名，注入、测试、备份、周报读取全部要分叉，且 `list_weekly_models()` 这类跨表查询会失去意义。一次性 schema 迁移的代价更小。

## 4. 估值双指标

`data/lixinger.py` 的指标从两个常量变成一张表：

```python
METRIC_SPECS = {
    "pe_ttm": ("pe_ttm.mcw", "pe_ttm.y10.mcw.cvpos"),
    "pb":     ("pb.mcw",     "pb.y10.mcw.cvpos"),
}
WINDOW = "y10"   # 已确认口径
```

一次请求带 4 个指标（`pe_ttm.mcw`、`pb.mcw`、`pe_ttm.y10.mcw.cvpos`、`pb.y10.mcw.cvpos`），解析出 `(metric, date, value, percentile_ratio)` 元组。`ValuationPoint` 增加 `metric` 与 `value` 字段，`pe_ttm` 字段保留为 `value` 的别名以兼容现有测试。

分位历史（供曲线用）：新增 `index_valuation_history(index_code, metric, window, date, value, percentile_ratio, PK(index_code,metric,window,date))`。首次采集用 `startDate = endDate - 10年` 回填整段（约 2400 行/指数），之后每日增量。`index_valuations` 保留为"最新合格快照"，避免读路径改动过大。

**分位一律取供应商 `cvpos`，不在本地重算**——这条既有决策不破。

## 5. 服务与接口

`ValuationService` 单例改为 `ValuationRegistry`：

```python
app.state.valuation_services: dict[str, ValuationService]   # code -> service
```

`ValuationService.__init__` 增加 `index_code` 参数，内部所有 `INDEX_CODE` 引用替换为 `self.index_code`。刷新入口 `refresh_all()` 顺序遍历两个指数，**单个失败只记录该指数的 reason，不影响另一个**（PRD R2）。

响应形状（R6 兼容）：

```jsonc
"valuation": {
  "target_date": "2026-11-19",
  "metrics": {
    "pb":     {"state":"ok","value":3.8,"percentile_pct":19.5,"as_of":"2026-11-19","captured_at":"..."},
    "pe_ttm": {"state":"ok","value":26.9,"percentile_pct":3.0,"as_of":"2026-11-19","captured_at":"..."}
  },
  // 兼容旧前端：PE 平铺字段保持不变
  "state":"ok","pe_ttm":26.9,"percentile_pct":3.0,"as_of":"...","reason":null
}
```

`_require_supported_index(code)` 改为查 `BY_CODE`，404 文案改为列出支持的代码。

新增 `/api/indices/{code}/valuation/history?metric=pb` 返回曲线数据（`{dates:[], values:[], percentiles:[]}`）；`metric` 白名单校验，非法值 400。

## 6. 前端

- `lib/api.ts`：`INDICES = ["000300","399673"]`，四个函数加 `code` 参数（默认 `000300`，避免一次性改页面多处调用）。
- 指数切换：页面顶部一个两选一（沪深300 / 创业板50），切换后重取 `status` + `chart`。
- 估值卡：PB 分位为主显示（大号），PE 分位为辅；指标切换只在曲线图上生效。
- 曲线图复用现有 ECharts 封装，一条 `percentile` 折线（0–100%），叠加 20/50/80 三条参考水平线。
- 遵循「让布局解释」：不加解释性副标题、不加 tooltip 整句说明。

## 7. 风险与回滚

| 风险 | 处置 |
|---|---|
| schema 迁移写坏现有 000300 数据 | 迁移前 `VACUUM INTO` 备份到 `data/backup-006-<ts>.db`；迁移单事务，失败自动回滚 |
| 理杏仁对 399673 返回空或字段缺失 | 沿用现有 `state=empty/no_data`，页面降级；不写 0 |
| 腾讯 `sz399673` 周K 起点晚于断言 | 断言用 `idx.earliest_weekly`，取值放宽 2 周并记日志 |
| 前端一次性改多处出错 | `code` 参数默认值兜底，旧调用路径行为不变 |

回滚点：`git revert` 该任务的单个提交即可——迁移是新增文件，不改既有数据语义。

## 8. 待评审

- 分位曲线是否纳入本期（PRD R5 的「形态」）：纳入则多 1 张表 + 1 个接口 + 1 个组件；砍掉则 R5 只剩数值展示。

---

## 实施记录（与设计的偏差，2026-11-19）

1. **不用 `ValuationRegistry`**：`ValuationService` 保持单实例，方法按 `index_code` 参数化。
   `index_code` 是**仅关键字参数**，`target_date` 仍是位置参数——旧调用 `refresh("2026-10-30")`
   不会把日期读成指数代码（这是实现过程中真实踩到的回归，已有测试守住）。
2. **metric key 沿用旧风格**：`pe_ttm_mcw` / `pb_mcw`，不引入 `pe_ttm` / `pb` 短名。
   好处是既有 `index_valuations` 行不用改 metric 就能回填进新表。
3. **旧 `weekly_data_meta` 没有 `index_code` 列**（只有 `id`）：迁移里对它是字面量 `'000300'`，
   不能对它做 `COALESCE(index_code, '000300')`。写测试时才暴露，已修正。
4. **`index_valuations` 保留为历史档案**，不再写入；读写改走 `index_valuation_history`
   （有独立 `value` 列，PB 不必塞进 `pe_ttm` 列），迁移时把旧 PE 行回填过去。
5. **固定窗口按 `inception_month` 过滤**：窗口起点早于指数发布月就跳过。
   用 `inception_week` 比会把沪深300 自己的第一个窗口（2005-04-01 vs 2005-04-04）误杀。
6. **`data=[]` 判 `empty` 不是 `error`**：`no_data` 单独识别，避免"没有数据"被读成"采集坏了"。
7. **顶层快照加 `value`**，`pe_ttm` 保留为别名：PB 也叫得通，同时不破坏既有读 `pe_ttm` 的调用方。
8. **顺手修掉 5 个预存失败**：`jobs_info()` 顺序断言依赖 APScheduler 集合顺序，
   改为排序后比较（`test_refresh_lifecycle`、`test_valuation_daily_job`）。
9. **前端构建**：`pnpm build` 编译与静态生成通过，Windows 上 `output: standalone` 复制软链报
   `EPERM`（环境权限），不影响应用；CI/Linux 不受影响。

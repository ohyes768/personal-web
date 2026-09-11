# Implement: 债基全量刷新 L6 阶段补写 fees/holdings

> 接 PRD 和 design.md，本文件是可被 `trellis-implement` 直接照着做的执行清单。
> 每步含**验证命令**和**回滚点**。

## 步骤 0：前置条件

```bash
# 确认设计稿存在
ls .trellis/tasks/09-11-bond-detail-fees-holdings-writeback/{prd.md,design.md,implement.md}

# 确认当前在 master 且工作树干净
git status --short
git rev-parse --abbrev-ref HEAD   # 应为 master
```

回滚点：本任务所有改动尚未开始，可直接 `task.py stop` 取消。

## 步骤 1：扩展 `refresh_market_full_sync` 参数与 main_run.total

**文件**：`backend/fund-select/src/services/market_full_pipeline.py`

**改动**：
1. 加 `pipeline_profile: str = "stock"` 参数（第 5 个位置参数后；line 154 附近）
2. 函数开头加取值校验：`if pipeline_profile not in ("stock", "bond"): raise ValueError(...)`
3. 加模块常量 `ACTIVE_STAGES` dict
4. 替换 `main_run.total = len(codes) * 6 if codes else 6`（line 192 和 line 273）
   改为 `main_run.total = len(codes) * len(ACTIVE_STAGES[pipeline_profile]) if codes else len(ACTIVE_STAGES[pipeline_profile])`
5. 更新 docstring 说明 profile 含义

**验证**：
```bash
cd F:/personal-projects/personal-web/backend/fund-select
python -c "from src.services.market_full_pipeline import refresh_market_full_sync; import inspect; print(inspect.signature(refresh_market_full_sync))"
# 应输出：(*, universe_filter=None, min_ret_3y=None, min_size_yi=None, min_mgr_exp=None, preset_task_id=None, pipeline_profile='stock')
```

回滚点：参数未生效，未跑过任何任务，revert 文件即可。

## 步骤 2：实现 `_stage_l6_fees_holdings` 与 `_fetch_one_fees_holdings`

**文件**：`backend/fund-select/src/services/market_full_pipeline.py`

**改动**：
1. 在 L3 之后（约 line 285）插入 profile 分支：
   ```python
   if pipeline_profile == "bond":
       stage_results["L6_fees_holdings"] = _run_stage(
           db, task_id, "L6_fees_holdings", len(codes), _stage_l6)
       _update_main_progress(len(codes),
                             failed=stage_results["L6_fees_holdings"].get("result", {}).get("failed", 0))
   else:
       # stock 路径保留原 L4 / L5
       stage_results["L4_risk"] = _run_stage(...)
       _update_main_progress(...)
       stage_results["L5_achievement"] = _run_stage(...)
       _update_main_progress(...)
   ```
2. 新增 `_stage_l6(d)` 与 `_fetch_one_fees_holdings(code, year)` 函数（模块顶部 `_stage_l0` 附近）
   - 完整代码见 [design.md](design.md) 的"L6 阶段实现细节"
3. 加 import：`from concurrent.futures import ThreadPoolExecutor, as_completed` 和
   `from src.data.fee_fetcher import fetch_fees` / `from src.data.holdings_fetcher import analyze_holdings, fetch_bond_hold` /
   `from src.services.refresh_service import persist_snapshot` / `from src.data.market_subtype_map import DISCOVERY_BOND_SUBTYPES`
   - **注意**：`persist_snapshot` 在同一文件可能会循环依赖，用 lazy import（函数内 import）

**验证**：
```bash
cd F:/personal-projects/personal-web/backend/fund-select
python -c "
from src.services.market_full_pipeline import _stage_l6_fees_holdings, _fetch_one_fees_holdings
print('L6 import OK')
"
# 期望输出：L6 import OK
```

回滚点：未跑过 L6 任务，revert 文件即可。

## 步骤 3：路由层加 `pipeline_profile="bond"`

**文件**：`backend/fund-select/src/api/routes.py`

**改动**：line 460 `refresh_market_full_sync(...)` 调用处加 `pipeline_profile="bond"` 参数

**验证**：
```bash
cd F:/personal-projects/personal-web/backend/fund-select
grep -n "pipeline_profile" src/api/routes.py
# 应在 line 460 附近看到 pipeline_profile=\"bond\"
```

回滚点：删掉这个 kwarg 即回到精简版（4 阶段）。

## 步骤 4：写 pytest 测试

**文件**：`backend/fund-select/tests/test_market_full_pipeline.py`（如不存在则新建）

**测试用例**（按 PRD 验收 A4-A7 + design.md 兼容性矩阵）：

| 用例 | 验证点 |
|---|---|
| `test_bond_profile_invokes_l6_only` | profile="bond" 时 L4_risk / L5_achievement 不调，L6_fees_holdings 调 |
| `test_stock_profile_invokes_l4_l5_not_l6` | profile="stock" 时 L4/L5 调，L6 不调 |
| `test_default_profile_is_stock` | 不传 profile → 默认 "stock" |
| `test_invalid_profile_raises` | profile="invalid" → ValueError |
| `test_bond_main_run_total_is_5_per_code` | profile="bond" 时 main_run.total = codes × 5 |
| `test_stock_main_run_total_is_6_per_code` | profile="stock" 时 main_run.total = codes × 6 |
| `test_l6_single_fund_failure_does_not_block_others` | 单只 fees 抛异常 → 该只 failed、其他 completed |
| `test_l6_filters_non_bond_subtypes` | market_subtype 不在 DISCOVERY_BOND_SUBTYPES 的 code 被过滤 |

**关键 mock 策略**：
- `refresh_market_full_sync` 跑起来太重（akshare 联网），测**只覆盖 _stage_l6 单元**
- mock `fetch_fees` / `fetch_bond_hold` / `persist_snapshot`，断言调用次数和参数
- 用 `db_session` fixture（已有 conftest）mock DB 写入

**验证**：
```bash
cd F:/personal-projects/personal-web/backend/fund-select
pytest tests/test_market_full_pipeline.py -v
# 期望 8 条全过
```

回滚点：测试失败不阻塞主路径（不修改 routes.py），删测试文件即可。

## 步骤 5：跑后端全套测试

**验证**：
```bash
cd F:/personal-projects/personal-web/backend/fund-select
pytest tests/ -v
# 期望既有测试不回归（除 L4/L5 跳过的 profile 相关测试可能需要更新）
```

回滚点：测试失败 = 改动有 bug，按错误修；不要靠删除测试通过。

## 步骤 6：手动验证（dev 跑一次小规模 profile="bond"）

**前置**：
- DB 已 seed 债基 universe（`market_universe_refresh` 跑过）
- 至少 50 只债基的 `funds.market_subtype` 已填

**验证**：
```bash
# 后端启动
cd F:/personal-projects/personal-web/backend/fund-select
./.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8095 --reload

# 前端另起
cd F:/personal-projects/personal-web/apps/fund-select
pnpm dev

# 触发：访问 /funds/discovery-bond，点"全量刷新"，min_ret_3y=10
# 观察后端日志：应该有 5 个 stage key：L0_universe / L1_rank / L2_size / L3_nav / L6_fees_holdings
# L6_fees_holdings 不应包含 L4_risk / L5_achievement

# DB 验证
python -c "
import sqlite3
conn = sqlite3.connect('data/fund_select.db')
print('fund_fees 债基行数:', conn.execute('SELECT COUNT(*) FROM fund_fees WHERE code IN (SELECT code FROM funds WHERE market_subtype LIKE \"债券型%\" OR market_subtype LIKE \"指数型-固收%\")').fetchone()[0])
print('fund_holdings_bond 债基行数:', conn.execute('SELECT COUNT(*) FROM fund_holdings_bond WHERE code IN (SELECT code FROM funds WHERE market_subtype LIKE \"债券型%\" OR market_subtype LIKE \"指数型-固收%\")').fetchone()[0])
"
# 期望 fund_fees 行数 >= universe 50%（东财反爬兜底），fund_holdings_bond 类似
```

回滚点：DB 写入错乱 → 立即停服务、回滚 commit、清表。

## 步骤 7：前端 0 改动验证

**验证**：
```bash
cd F:/personal-projects/personal-web
git diff apps/  # 应为空
```

## 步骤 8：提交 + 推送

```bash
cd F:/personal-projects/personal-web
git add backend/fund-select/src/services/market_full_pipeline.py \
        backend/fund-select/src/api/routes.py \
        backend/fund-select/tests/test_market_full_pipeline.py

# 注释风格：conventional commits（按 CLAUDE.md）
git commit -m "feat(fund-select): 债基·市场全量刷新补写 FundFees + FundHoldingsBond，让详情页自给自足

- market_full_pipeline 新增 L6_fees_holdings 阶段（仅 profile=bond 触发）
- 复用 fetch_fees + fetch_bond_hold fetcher + persist_snapshot 写入路径
- 5 worker 并发 + 单只失败容错（对齐 market_nav_fetcher 限流策略）
- profile=bond 阶段序列：L0/L1/L2/L3/L6（5 阶段），stock 维持 6 阶段
- 详情页（fundApi.getDetail）现在只跑债基·市场刷新也能拿到完整数据
- 测试：8 条 pytest 覆盖 profile 分支 / L6 单只失败容错 / 非债基过滤"
git push origin master
```

## 步骤 9：归档 `09-11-bond-full-refresh-default-10pct` 脏任务

```bash
cd F:/personal-projects/personal-web
python .trellis/scripts/task.py archive 09-11-bond-full-refresh-default-10pct
```

**验证**：
```bash
python .trellis/scripts/task.py list | grep "09-11"
# 期望：只剩本任务（当前 active）和 default-10pct 已归档不在列表
```

## 完成判定

| 项 | 期望 |
|---|---|
| 步骤 1-7 验证全过 | 是 |
| git status 干净 | 是 |
| git push 成功 | 是 |
| 4 个 Trellis 脏任务（3 个 09-10 + 09-09）已归档 | 是 |
| 09-11-bond-full-refresh-default-10pct 已归档 | 是 |
| 本任务可 archive | 是（按 Phase 3.5 走 `/trellis:finish-work`） |

## 关键回滚点（汇总）

| 阶段 | 回滚动作 | 影响范围 |
|---|---|---|
| 步骤 1-3 完成后 | `git revert HEAD` | 全部改动 |
| 步骤 4-7 完成后 | `git revert HEAD` + 测试文件保留 | 回到精简版 |
| 步骤 8 推送后 | `git revert HEAD && git push` | 生产回滚 |
| DB 写入错乱 | 删 `fund_fees` / `fund_holdings_bond` 表债基行 + 任务 archive | 详情页临时无数据 |
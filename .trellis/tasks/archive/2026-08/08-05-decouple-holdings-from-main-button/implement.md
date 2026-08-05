# Implement: 股息率按钮状态机重构

> 顺序按"先抽公共函数 → 改主路径 → 加新副作用 → 改接口 → 改前端"。每步都有验证命令、review gate、rollback 兜底。

## Step 0：基线（任何改动之前）

**目的**：按 MEMORY.md "改动前必须跑基线"原则，确认改动前的失败/错误不属于本次改动引入。

```bash
cd backend/dividend-select
git stash push -- src/ main.py tests/  # 或具体改动路径
python -m pytest tests/ -v > /tmp/baseline.txt 2>&1
git stash pop
```

**Review gate**：把 `/tmp/baseline.txt` 里失败的测试记下来。Step 1-7 之后对比，新增失败 = 回归。

---

## Step 1（FR-3 抽写盘公共函数）

**目标**：抽出 `_persist_prefilter_stock_list(stock_items, date_str)`，写单测确认与原实现输出一致。

**改文件**：
- `backend/dividend-select/src/api/routes.py`：新增函数（约 line 1730 之后，紧邻 refresh_dividend）

**实施**：
1. 函数体（4 行等价）：
   ```python
   def _persist_prefilter_stock_list(stock_items, date_str: str) -> None:
       """把 prefilter 后的股票代码单列写盘。stock_items 可含 StockBasicInfo 或 str。"""
       from src.utils.helpers import save_csv_data
       codes = [
           str(s.code if hasattr(s, "code") else s).zfill(6)
           for s in stock_items
       ]
       if not codes:
           raise ValueError("prefilter stock_list 为空，拒绝写空文件")
       prefilter_df = pd.DataFrame([{"股票代码": c} for c in codes])
       save_csv_data(prefilter_df, "prefilter_stock_list", date_str)
       logger.info(f"prefilter stock_list 已写盘: {len(codes)} 只")
   ```
2. docstring 含 commit `3c1dce4` 口径引用

**验证**：
```bash
cd backend/dividend-select
python -c "import ast; ast.parse(open('src/api/routes.py').read()); print('OK')"
pytest tests/test_persist_prefilter.py -v
```

**新增测试** `test_persist_prefilter.py`：
- `test_basic_stock_basic_info_list`：传入 `list[StockBasicInfo]`，验证 CSV 单列、6 位前导 0
- `test_string_list_input`：传入 `list[str]`，同样行为
- `test_deduplication_not_handled`：函数**不去重**（dedup 是调用方职责），验证输入重复则输出重复
- `test_empty_raises`：空 list raise ValueError
- `test_csv_path_and_header`：CSV 路径包含 `data/{date_str}/prefilter_stock_list_{date_str}.csv`，列名 `股票代码`

**Review gate**：新测试全绿 + Step 0 基线没新增失败。

**Rollback**：revert 该 commit。函数未调用 → 无副作用。

---

## Step 2（FR-3 替换 refresh_dividend + main.py）

**目标**：把抽出的函数接到 refresh_dividend（routes.py:1838-1841）和 main.py:166-168，避免"双重写盘实现漂移"。

**改文件**：
- `backend/dividend-select/src/api/routes.py::refresh_dividend` 约 1838-1841 行
- `backend/dividend-select/main.py` 约 166-168 行

**实施**：
1. routes.py:1838-1841 三行 → 改为 `_persist_prefilter_stock_list(stock_list, date_str)`
2. main.py:166-168 同款 → 改为 `_persist_prefilter_stock_list(stock_list, date_str)`
3. 删除 `from src.utils.helpers import save_csv_data` 在 routes.py 那一处（如果只是这一处用）

**注意（写盘行为 1:1 兼容）**：
- 文件名规范保持：`prefilter_stock_list_{date_str}.csv`（`save_csv_data` 会自动加日期 + .csv）
- 列名保持：`股票代码`
- 类型：str，zfill(6)
- log 文案保持一致

**验证**：
```bash
cd backend/dividend-select
python -m pytest tests/ -v --continue-on-collection-errors
python -c "import ast; ast.parse(open('src/api/routes.py').read()); print('OK')"
python -c "import ast; ast.parse(open('main.py').read()); print('OK')"
```

**手动烟测**（可选，本地能跑就跑）：
```bash
curl -X POST http://127.0.0.1:8092/api/dividend/refresh -d '{}'  # 跑全量
wc -l data/$(date +%Y-%m)/prefilter_stock_list_*.csv  # 输出行数与之前对比
```

**Review gate**：pytest 全绿（与基线对比无新增失败）+ AST parse 通过 + 写盘行数与上一次全量刷一致（±1 因 index 调仓波动）。

**Rollback**：revert 该 commit。

---

## Step 3（FR-1 删 `or not holdings_complete`）

**目标**：主按钮 needs_update 不再受持仓覆盖度影响。

**改文件**：
- `backend/dividend-select/src/api/routes.py:1717`
- `backend/dividend-select/src/api/routes.py:1601`（docstring）

**实施**：
1. line 1717 改为 `needs_update = completed_count < target_count`
2. line 1601 docstring 删 "或持仓指数覆盖不全"
3. 注释里加：commit 423d2fe 的修复被本 commit 取消，对比 2 由 IndexStatusPopover 接管（commit XXXX 引用）

**新增测试** `test_status_needs_update.py`：
- `test_no_holdings_override`：
  - mock 持仓 CSV 让其缺 `931468`
  - prefilter CSV 144 行 + 近3年股息率 CSV 144 行
  - GET `/dividend/status`
  - 验收 `needs_update=false`（因为 144 == 144）
  - 行为对照：改动前同一个 setup 会因 `not holdings_complete=True` → needs_update=true

**验证**：
```bash
cd backend/dividend-select
pytest tests/test_status_needs_update.py -v
pytest tests/ -v  # 整个
```

**Review gate**：新测试通过 + 旧测试无回归。

**Rollback**：revert 该 commit。

---

## Step 4（FR-2 + FR-4 单指数刷加 prefilter 重算 + 扩响应）

**目标**：单指数刷成功后本地重算 prefilter；接口响应加 `prefilter_resynced` + `prefilter_error` 字段。

**改文件**：
- `backend/dividend-select/src/api/routes.py::refresh_single_index_holdings`（约 1943-1996）
- `backend/dividend-select/src/api/models.py` 或 `routes.py` 内联 `IndexRefreshItem`

**实施**：
1. 先确认 models.py 有没有 `IndexRefreshItem`，如果没有则在 routes.py 用 pydantic model
2. `IndexRefreshItem` 加两字段
3. 在 `fetcher.replace_one_holdings(request.code)` **返回 success=True 之后**加 try/except 块：
   ```python
   prefilter_resynced = False
   prefilter_error = None
   try:
       # 读 汇总 + fhps，重算，写盘
       ...
       prefilter_resynced = True
   except Exception as e:
       logger.error(f"单指数刷持仓成功但 prefilter 重算失败: code={request.code}, err={e}")
       prefilter_error = str(e)[:200]   # 截断防止泄露
   ```
4. `result` dict 加 `prefilter_resynced` + `prefilter_error` 后再传 `IndexRefreshItem(**result)`

**新增测试** `test_single_index_refresh.py`：
- `test_updates_prefilter`：mock akshare + 准备 fixture CSV → 调接口 → 验证 prefilter CSV 更新 + response `prefilter_resynced=true`
- `test_no_akshare_call`：mock `akshare.*` 任意入口不抛错
- `test_prefilter_failure`：
  - 破坏汇总 CSV → mock 让 fetcher 报 success=True 但实际写坏 → 验证
  - 或者：mock `_compute_prefilter_stock_list` 抛 ValueError
  - 验收：response `success=true, prefilter_resynced=false, prefilter_error="..."`

**验证**：
```bash
cd backend/dividend-select
pytest tests/test_single_index_refresh.py -v
pytest tests/ -v
python -c "import ast; ast.parse(open('src/api/routes.py').read()); print('OK')"
```

**Review gate**：3 个新测试全绿 + 整个测试无回归 + AST 通过。

**Rollback**：revert 该 commit。

---

## Step 5（前端 types.ts 加字段）

**目标**：`IndexRefreshItem` 类型加 `prefilter_resynced` + `prefilter_error`。

**改文件**：
- `apps/dividend/src/lib/types.ts` line 272

**实施**：
1. 在现有 `error?: string | null` 之后加：
   ```ts
   /** 单指数刷新后是否完成 prefilter 本地重算。徽章显示 ✅ 需要为 true。 */
   prefilter_resynced: boolean;
   /** prefilter 重算失败原因（仅 prefilter_resynced=false 时有意义） */
   prefilter_error?: string | null;
   ```
2. docstring 注释（保留项目其他类型的风格）

**验证**：
```bash
cd apps/dividend
pnpm exec tsc --noEmit   # 类型检查，应有"已对齐旧响应"的兼容检查通过
pnpm lint
```

**Review gate**：tsc 0 error，lint 0 warning（新加字段算有用改动，不该有 warning）。

**Rollback**：revert 即可。

---

## Step 6（前端 page.tsx::getRowState 加严）

**目标**：单指数行显示 ✅ 改为 `success && prefilter_resynced`。

**改文件**：
- `apps/dividend/src/app/page.tsx` line 74-80

**实施**：
1. line 77 改为：
   ```ts
   const isFullSuccess = irItem.success && irItem.prefilter_resynced;
   return isFullSuccess
     ? { kind: 'refreshed_success', item: irItem }
     : { kind: 'refreshed_failed', item: irItem };
   ```
2. 触发按钮统计（line 91-97）的 `successCount` 自动跟随 state 变化，无需改
3. 第 170 行 `<span>✓ {state.item.constituents_count}只</span>` 自动跟随 state.kind，无需改

**渲染文案增强**（可选 follow-up，不在本次必须）：
- line 173-178 失败展示可改：error 显示优先选 `prefilter_error`（如果是 prefilter 失败更直观）

```ts
title={
  state.item.prefilter_error
    ? `持仓成功但 prefilter 重算失败：${state.item.prefilter_error}`
    : state.item.error || '失败'
}
```

**验证**：
```bash
cd apps/dividend
pnpm exec tsc --noEmit
pnpm lint
```

**Review gate**：tsc/lint 通过。

**Rollback**：revert 该 commit。

---

## Step 7（端到端浏览器手动验证）

**前置**：本地启动前后端 (`scripts/start-dividend-dev.bat` 等价步骤)

| 场景 | 操作 | 验收 |
|---|---|---|
| A. 全量刷新成功 | 全量刷 → 看主按钮 + 徽章 | 主按钮灰（✅已是最新）；所有徽章 ✅ |
| B. 单指数刷持仓成功 + prefilter 成功 | 找一只正常指数点徽章重试 | 该指数 ✅；主按钮状态由对比 1 决定（与"持仓成功"等价） |
| C. 单指数刷持仓成功 + prefilter 失败 | 手动破坏汇总 CSV → 调接口 | 该指数 ✗ + 重试按钮（error 含 prefilter 字样）；主按钮根据 prefilter CSV 状态（仍保留旧 prefilter，target 不变）|
| D. 单指数刷持仓失败 | akshare 接口故障 mock | 该指数 ✗ + 旧逻辑（前置兼容）|

**Review gate**：4 个场景全部符合预期。

**Rollback**：若场景 B/C 不符合，回到 Step 6 调整；Step 5/6 都可独立 revert。

---

## Step 8（commit & push 子模块）

按 Commit Message Format：

```bash
cd backend/dividend-select
git add src/api/routes.py main.py tests/test_compute_prefilter.py
git commit -m "refactor(prefilter): 抽 _compute_prefilter_stock_list 公共函数

- 8 指数持仓并集 ∩ fhps 分红预案 → list[str]
- routes.py::refresh_dividend 和 main.py 同时接入
- 与 commit 3c1dce4 口径保持一致

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

git add src/api/routes.py tests/test_status_needs_update.py
git commit -m "fix(dividend/status): 移除非主按钮的持仓覆盖度判断

- needs_update = completed_count < target_count（去 or not holdings_complete）
- 持仓覆盖度由 IndexStatusPopover 接管
- 取消 commit 423d2fe 的临时绑定

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

git add src/api/routes.py tests/test_single_index_refresh.py
git commit -m "feat(dividend/index-holdings): 单指数刷成功后本地重算 prefilter

- 持仓刷新成功 → 本地读汇总 CSV + fhps → 重算 prefilter → 写盘
- 不调 akshare，纯本地合并
- 接口响应加 prefilter_resynced + prefilter_error 字段
- prefilter 重算失败 → logger.error 不抛出，返回 partial 状态

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

git push origin main
```

**注意（按 MEMORY.md submodule 实战流程）**：
- 只 add 自己改的文件，**别 add `.`**
- 用 `git submodule status backend/dividend-select` 验证 gitlink 还没动

**Review gate**：`git push` 成功 + 远端能看到 commit。

---

## Step 9（主仓库 gitlink bump）

```bash
cd /F/github/person_project/personal-web
git add backend/dividend-select
git commit -m "chore: bump dividend-select 状态机重构

- 抽 _compute_prefilter_stock_list 公共函数
- 主按钮 needs_update 移除持仓覆盖度判断
- 单指数刷成功后本地重算 prefilter

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
git push origin master
```

**Review gate**：远端 commit 可见。

---

## Step 10（前端 commit & push）

```bash
cd apps/dividend
git add src/lib/types.ts src/app/page.tsx
git commit -m "refactor(dividend): IndexStatusPopover success 条件加严

- IndexRefreshItem 加 prefilter_resynced + prefilter_error 字段
- getRowState 成功判定改为 success && prefilter_resynced
- 徽章 ✅ 仅在持仓+prefilter 都成功时显示

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

cd ..
git add apps/dividend
git commit -m "chore: bump 前端 IndexStatusPopover 状态机加严"
git push origin master
```

---

## Step 11（部署：本地 + NAS）

按 CLAUDE.md 子模块部署四件套（memory 里踩过的坑）：

```bash
git pull
git submodule update --init --recursive
docker compose build --no-cache dividend-backend dividend-frontend
docker compose up -d --force-recreate dividend-backend dividend-frontend
docker compose logs -f --tail 100 dividend-backend
```

**Review gate**：
- 后端启动日志无 ERROR
- curl 一下 status 接口返回字段包含 `holdings_status` 且 `needs_update` 行为正确
- 浏览器进去实际点几下徽章重试 + 看主按钮

---

## 回滚手册（如果出大问题）

| 问题 | 步骤 |
|---|---|
| Step 1-4 任一步失败 | revert 对应 commit，回到基线 |
| Step 5-6 前端 ts 失败 | revert 对应 commit |
| Step 7 e2e 行为不符 | 调整 getRowState / 回退 Step 6 |
| 部署后线上 500 | `docker logs` 看具体 stack trace，先 `docker compose down dividend-backend` 回退到上个版本 |
| prefilter 大量失败 | 临时 `setLogLevel DEBUG` 看具体 stock list 路径；如果系统性问题 revert Step 4 |

---

## 完成度 check

- [ ] Step 0 基线跑完，记下失败列表
- [ ] Step 1 抽函数 + 测试通过
- [ ] Step 2 改两处调用 + AST 通过
- [ ] Step 3 改 routes.py:1717 + 新测试通过
- [ ] Step 4 单指数刷加副作用 + 3 个新测试通过
- [ ] Step 5 前端 types.ts 加字段
- [ ] Step 6 前端 page.tsx::getRowState 加严
- [ ] Step 7 端到端 4 场景全过
- [ ] Step 8 后端子模块 3 commits push
- [ ] Step 9 主仓库 gitlink bump push
- [ ] Step 10 前端 commit+push
- [ ] Step 11 部署四件套 + 验证
- [ ] 更新 spec（按 Phase 3.3）+ memory（`dividend-button-state.md` 补后端 + commit 423d2fe + 接口契约）

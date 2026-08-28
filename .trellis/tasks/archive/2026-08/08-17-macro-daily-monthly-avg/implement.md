# 实施计划

前置：`prd.md`(需求/验收) + `design.md`(技术设计)已评审。
执行顺序按依赖排列，每步带验证命令。

## 步骤清单

### 1. 后端模型 + 透传 `[后端]`

- [ ] `backend/macro/src/models.py`:
  `MacroIndicator` 增加 `month_avg: Optional[float] = None`
- [ ] `backend/macro/src/services/macro_signal_service.py`:
  - `_convert_dimension_from_macro_signal`: 指标循环里读
    `m.get("month_avg")`，数值类型检查后传入构造
  - `_convert_risk_appetite`: 三个子块同样读 `block.get("month_avg")`
- 验证：`cd backend/macro && python -m pytest tests/ -v`

### 2. 后端测试 `[后端]`

- [ ] `backend/macro/tests/test_macro_signal_month_avg.py` 新建，
  覆盖 design.md §5 的 4 个用例(透传/缺失/风险数据/非数值)
- 验证：`python -m pytest tests/test_macro_signal_month_avg.py -v`

### 3. 前端类型 + 展示 `[前端]`

- [ ] `apps/macro/src/lib/modules/macro-signal/types.ts`:
  `MacroIndicator` 增加 `month_avg?: number | null`
- [ ] `apps/macro/src/app/modules/economic/components/macro-signal/GroupCard.tsx`:
  `IndicatorRow` 内实现分层展示(design.md §3.2):
  - `isCurrentMonth` 判断
  - `showMonthAvg` 分支：主数值位/标签切换
- 验证：`cd apps/macro && pnpm lint`

### 4. 文档 `[文档]`

- [ ] `backend/macro/docs/MACRO_SIGNAL_API.md`: month_avg 字段契约
  (来源两处、类型、何时有值、当月/历史月展示语义)
- [ ] `backend/macro/docs/宏观信号按月留存设计.md` §8 场景表补一行:
  日频 skill 日度推送的行为说明；或新增调度约定小节
- 验证：人工评审

### 5. 收尾 `[流程]`

- [ ] 全量回归：后端 pytest 全绿 + 前端 lint 通过
- [ ] 手动验证 AC3/AC4(本地起 dev,造带 month_avg 的 JSON 看历史月/当月展示)
- [ ] Trellis 3.3 spec 更新(如有可沉淀契约) → 3.4 commit

## 回滚点

- 每步独立可回滚：字段透传是纯增量，回滚 = revert 对应 commit。
- 前端展示分层逻辑独立成组件内小函数，不影响现有渲染路径。

## 明确不做

- skill 侧 month_avg 计算逻辑(macro-fin-skill 仓库)
- B 方案的 cron 脚本实现(部署侧，仅文档登记约定)
- `updated_at` 别名清理(独立任务)

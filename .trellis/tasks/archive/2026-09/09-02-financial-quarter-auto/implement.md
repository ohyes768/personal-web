# 实施计划：财务指标季度口径自动切换

## 步骤

### 1. 后端 fetcher：重写 `_calc_quarterly_yoy`
- [ ] 删除 `QUARTERLY_YOY_REPORT_DATE` / `QUARTERLY_YOY_BASE_DATE` 常量及注释
- [ ] 新实现：每只股票取最新报告期，单季还原（Q2/Q3/Q4 减同年上一累计期），
      同比 vs 去年同期单季；返回值增加 `"数据季度"`
- [ ] `fetch_one`：删除 `result["数据季度"] = current_quarter()` 及其 import
      （`current_quarter` 若无其他引用则连 import 一起删；`aux_file_path` 保留）
- 验证：`python -m pytest tests/test_financial_fetcher.py -v`（先改测试，见步骤 3 TDD 顺序可并行）

### 2. 后端 API 链路透传
- [ ] `shareholder_financial_reader.py` `FinancialReader.get_stock_data`：
      增加 `latest_quarter_label`（读 CSV `数据季度` 列）
- [ ] `routes.py` 两处 `financial_map` 构造（`:453`、`:2229`）透传
      `latest_quarter_label`
- [ ] `routes.py` `_row_to_stock_model`（`:284` 附近）赋值到模型
- [ ] `models.py` `DividendStock` 新增
      `latest_quarter_label: Optional[str] = Field(None, description="最新季度扣非数据所属报告期，如 2026Q2")`
      并更新 `:104-105` 两条字段的过时描述（"2026Q1" 字样）
- 验证：`python -m pytest tests/ -v`（全量后端测试）

### 3. 测试重写（与步骤 1 配合，先写用例）
- [ ] 重写 `TestCalcQuarterlyYoy`：删常量 import，按 design.md「测试设计」8 条用例
- 验证：`python -m pytest tests/test_financial_fetcher.py -v` 全绿

### 4. 前端
- [ ] `types.ts`：`DividendStock` 加 `latest_quarter_label?: string | null`
- [ ] `DividendTable.tsx` 三处（:492 title / :692 标题 / :696 副标题）改动态，
      null 时 fallback `最新季度`
- 验证：`cd apps/dividend && pnpm build`

### 5. 收尾
- [ ] `grep -rn "2026Q1\|2026Q2"` 确认前端与后端模型无残留写死文案
- [ ] trellis-check 子代理全量检查
- [ ] spec 更新 + 提交（feat(dividend-select): 财务指标季度口径自动切换）

## 回滚点

每个步骤独立可 revert；步骤 1-3 为一个后端单元，步骤 4 为前端单元。

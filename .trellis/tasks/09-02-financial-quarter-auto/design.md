# 技术设计：财务指标季度口径自动切换

## 数据事实（已验证）

akshare `stock_financial_analysis_indicator` 返回的
`扣除非经常性损益后的净利润(元)` 为**报告期累计值**：
- 03-31 行 = Q1 单季（累计=单季）
- 06-30 行 = 上半年累计
- 09-30 行 = 前三季累计
- 12-31 行 = 全年累计

单季还原：`单季(Q2) = 累计(06-30) − 累计(03-31)`，Q3/Q4 同理。

## 改动边界

| 文件 | 改动 |
|------|------|
| `backend/dividend-select/src/data/financial_fetcher.py` | 重写 `_calc_quarterly_yoy`；删两个常量；`数据季度` 取自实际报告期 |
| `backend/dividend-select/src/services/shareholder_financial_reader.py` | `FinancialReader.get_stock_data` 增加 `latest_quarter_label` |
| `backend/dividend-select/src/api/routes.py` | 两处 `financial_map` 构造透传 `latest_quarter_label`；`_row_to_stock_model` 赋值 |
| `backend/dividend-select/src/api/models.py` | `DividendStock` 新增 `latest_quarter_label: Optional[str]` |
| `backend/dividend-select/tests/test_financial_fetcher.py` | 重写 `TestCalcQuarterlyYoy`；新增数据季度断言 |
| `apps/dividend/src/lib/types.ts` | `DividendStock` 增加 `latest_quarter_label?: string \| null` |
| `apps/dividend/src/components/DividendTable.tsx` | 3 处写死文字改用字段，缺字段时 fallback |

## 核心算法：`_calc_quarterly_yoy(df)` 新逻辑

```
输入 df 含 日期 + 扣除非经常性损益后的净利润(元)（累计值，含季报+年报行）

1. 取"最新报告期" = max(日期) 中属于季报月份(3/6/9/12月末日)的那一行 R
   （akshare 该接口只返回报告期行，max 即最新，无需额外过滤）
2. 单季值计算（不跨年：Q1 直接取；Q2/Q3 减同年上一报告期；
   Q4=12-31 减同年 09-30）：
   Q1: single = R
   Q2/Q3/Q4: single = R − 同年上一报告期累计（缺上一期 → None）
3. 去年同期单季值：same = 去年同月份报告期累计 − 去年上一报告期累计
   （去年同期行缺失 → None；Q1 时 same = 去年 03-31 行）
4. 返回 {
     "最新季度扣非(元)": single,
     "最新季度扣非同比(%)": (single − same) / abs(same) * 100  （任一为 None 或 same==0 → None）,
     "数据季度": f"{year}Q{q}"（R 对应季度）,
   }
```

注意点：
- `_calc_quarterly_yoy` 内部直接产出 `数据季度`，`fetch_one` 里
  `result["数据季度"] = current_quarter()` 一行删除（该 import 同时被
  `fetch_and_save` 用于文件名，`aux_file_path` 的 import 保留）。
- `数据季度` 移入 quarterly_metrics 返回，保持 fetch_one 结构不变。
- 基数为负：沿用现状 `(single-same)/abs(same)*100`（现状 Q1 也这么算）。
- akshare 日期列可能为 `datetime.date` 或字符串，统一 `pd.to_datetime(...).dt.date`。

## 前端展示

- `DividendTable.tsx:492` hover title：`点击查看 {label} 扣非同比`
- `DividendTable.tsx:692` 弹层标题：`{label} 扣非同比`
- `DividendTable.tsx:696` 副标题：`vs {prevYearLabel}`
  （后端直接下发 `latest_quarter_label="2026Q2"`，
   前端 `label.replace(/\d{4}/, y => y-1)` 推导同期，不加第二个字段）
- label 为 null（老 CSV 行、无季报数据）：标题显示 `最新季度 扣非同比`、
  副标题省略，弹层仍可打开（yoy 有值的前提）。

## 兼容性

- 旧 CSV 无新语义（`数据季度` 是日历季度、yoy 是 Q1 口径）：字段缺省时前端
  fallback 显示，不报错；`get_quarter()` 沿用 `sorted()[-1]`，"2026Q3" >
  "2026Q2" 字典序恰好等于时间序，status 接口无需改。
- `routes.py:1034` 的 `current_quarter_date`（missing_count 判定）逻辑独立、
  语义为"当季数据日期"，本次不动（它基于 `数据日期` 列，不受影响）。
- CSV 列集合不变（`数据季度` 复用），旧文件可继续被读。

## 测试设计

重写 `TestCalcQuarterlyYoy`（引用常量删除，测试改用真实日期字面量）：
1. 最新期 06-30：单季 = H1−Q1，同比 vs 去年（H1'−Q1'）
2. 最新期 03-31（Q1）：单季=Q1，同比 vs 去年 Q1（回归旧口径行为）
3. 最新期 12-31（Q4/年报）：单季 = FY − Q3累计
4. 新股只有 2026Q1、无 2025 数据：绝对值有、同比 None、数据季度 2026Q1
5. 缺同年上一累计期（如有 06-30 无 03-31）：同比 None
6. 基数为 0：None（防除零）
7. Regression guard：真实 akshare 列名 + `datetime.date` 类型日期
8. `数据季度` 值断言（Q2 场景 → "2026Q2"）

## 回滚

单仓库普通提交，`git revert` 即可。无 DB/schema 变更，CSV 列集合不变。

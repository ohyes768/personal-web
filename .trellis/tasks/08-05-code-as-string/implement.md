# Implement: 股票代码/指数代码全链路 string 化

前置阅读顺序：`prd.md` → `design.md` → 本文件。

## 执行清单

### Step 1 — 定义统一常量

- [ ] `src/utils/helpers.py` 顶部（`DATA_DIR` 附近）新增 `CODE_DTYPE`
- [ ] 确认 `load_csv_data` 的 `dtype` 参数 docstring 与新常量表述一致

**验证**：`python -c "from src.utils.helpers import CODE_DTYPE; print(CODE_DTYPE)"`

---

### Step 2 — P0：申万 `.str` accessor 隐患（2 处）

- [ ] `src/data/board_loader.py:65` → `pd.read_csv(..., dtype=CODE_DTYPE)`
- [ ] `src/services/stock_info_service.py:42` → 同上

这两处 `.str.replace(r"\.(SZ|SH)$", ...)` 当前依赖"CSV 里恰好有带后缀的行"才没抛
`AttributeError`。补 dtype 后不再依赖数据侥幸。

**验证**：
```bash
python -c "
from src.services.stock_info_service import StockInfoService
s = StockInfoService(); print(s.get_stocks_info(['000090','000523']))
"
```
两只股票的申万行业字段应非空。

---

### Step 3 — P0：`append_csv_row` 混合类型列

- [ ] `src/utils/helpers.py:303` → `pd.read_csv(filepath, encoding="utf-8-sig", dtype=CODE_DTYPE)`

**验证**（构造前导零样例，确认落盘格式一致）：
```bash
python -c "
from src.utils.helpers import append_csv_row, load_csv_data, CODE_DTYPE
append_csv_row({'股票代码':'000099','x':1}, '_dtype_probe.csv', '_test')
append_csv_row({'股票代码':'600000','x':2}, '_dtype_probe.csv', '_test')
df = load_csv_data('_dtype_probe.csv', '_test', dtype=CODE_DTYPE)
print(df['股票代码'].tolist())   # 期望 ['000099', '600000']
"
```
跑完删除 `data/_test/_dtype_probe*.csv`。

---

### Step 4 — P0：CLI 显示

- [ ] `display_results.py:30` → 补 `dtype=CODE_DTYPE`

**验证**：`python display_results.py | head -20`，代码列显示 6 位含前导零。

---

### Step 5 — P1：分红详情反向适配（**必须与 Step 6 同批，否则失配**）

- [ ] `src/core/calculator.py:489` → `load_csv_data("分红详情.csv", date_str, dtype=CODE_DTYPE)`
- [ ] `src/core/calculator.py:493` → 改为 str 比较：
      `df[df["股票代码"].astype(str).str.zfill(6) == str(code).zfill(6)]`
- [ ] 删除 492 行误导性注释"（CSV中股票代码是int类型）"

**验证**：对一只已有分红详情缓存的前导零股票调用 `_load_dividend_detail_from_csv`，返回非 None。

---

### Step 6 — 其余读入口补 dtype

- [ ] `src/services/data_reader.py:76`
- [ ] `src/services/shareholder_financial_reader.py:40`
- [ ] `src/services/shareholder_financial_reader.py:101`
- [ ] `src/data/board_loader.py:46`
- [ ] `src/services/m120_service.py:382`
- [ ] `src/services/m120_service.py:424`
- [ ] `src/services/m120_service.py:490`
- [ ] `src/utils/helpers.py:341`

**保留**所有既有 `astype(str).str.zfill(6)` 补偿，不做清理（见 prd 非目标）。

**验证**（确认无遗漏裸 read_csv）：
```bash
grep -rn "pd.read_csv" src/ *.py | grep -v "dtype"
```
输出应只剩不含代码列的 CSV 读取。

---

### Step 7 — 全量回归

- [ ] `python -m pytest tests/ -v`
- [ ] 起后端 `python -m uvicorn src.main:app --reload --port 8092`
- [ ] `curl -s localhost:8092/api/dividend/stocks | python -m json.tool | head -40`
- [ ] 抽查前导零股票（`000090` 等）的 `code` 为 6 位字符串，
      且 board / sw_industry / shareholder / financial 字段非空

**回归红线**：分红详情、申万行业、板块信息、股东户数、财务指标五类字段
在改动后不得出现新的空值。

---

### Step 8 — 沉淀规范文档

- [ ] 新建 `.trellis/spec/backend/dividend-select/backend/code-type-guidelines.md`
- [ ] 更新同目录 `index.md` 索引表，加入该条目

文档需覆盖：
1. 核心契约（代码类字段恒为 6 位 str）
2. 读入口必须传 `CODE_DTYPE`
3. 写盘前必须 `zfill(6)`
4. 禁止模式：裸 `pd.read_csv` 读代码列、`int(code)` 比较、
   无 dtype 保障下用 `.str` accessor
5. 本次踩坑实录（int64 推断、混合类型列、`.str` 侥幸）作为 case 附录

---

### Step 9 — 提交

子模块两阶段提交（见 CLAUDE.md 子模块管理规范）：

- [ ] `cd backend/dividend-select` → 只 add 本次改动文件 → commit → `git push origin main`
- [ ] 回主仓库 → `git add backend/dividend-select .trellis/` → commit → `git push origin master`

顺序不可颠倒：子模块必须先 push，主仓库 gitlink 才有效。

## 回滚点

- Step 5 完成后若分红详情异常 → 单独 revert Step 5，其余改动不受影响
- 整体异常 → `git revert` 子模块 commit，无数据迁移需回滚

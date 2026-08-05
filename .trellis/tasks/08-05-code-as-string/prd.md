# PRD: 股票代码/指数代码全链路 string 化规范

## 背景

`data/个股板块映射_2026Q2.csv` 里写的是 `000090`，`pd.read_csv` 不带 `dtype` 读回来变成 int64 的 `90`。
全仓实测（2026-08-05）：

| CSV | 代码列 | 读回 dtype | 样例 |
|-----|--------|-----------|------|
| 个股板块映射_2026Q2 | 股票代码 | **int64** | `90`, `157` |
| 股东户数汇总_2026Q2 | 股票代码 | **int64** | `2054`, `2055` |
| 财务指标汇总_2026Q3 | 股票代码 | **int64** | `157`, `651` |
| 红利指数持仓汇总_2026-08 | 股票代码 / 来源指数代码 | **int64** | `600000` / `999999` |
| 个股申万行业映射_2026Q2 | 股票代码 | object(str) | `'000523'` — **侥幸**，见下 |

写盘时是对的（带前导零），**问题全部出在读回环节**。

当前之所以线上没大面积报错，是因为代码里散落着约 25 处 `astype(str).str.zfill(6)` 做事后补偿。
这是一种"每个调用方都必须记得补偿"的脆弱契约：**补偿漏一处，就静默出错**。

## 问题定性

这不是"修 N 个 bug"，而是**消除一个脆弱契约**。三类问题：

### P0 — 真实潜伏 bug

1. **`board_loader.py:67` / `stock_info_service.py:44`**
   `self._sw_df["股票代码"].str.replace(...)` 在无 `dtype` 的列上直接用 `.str` accessor。
   当前申万 CSV 恰好被推断为 object 才没炸。一旦某季度数据全是纯数字 → int64 → `.str` 抛
   `AttributeError` → 被外层 `except` 静默吞掉 → **申万行业信息整体变空，且无任何报错**。

2. **`display_results.py:30`** 读完既无 `dtype` 也无 zfill 补偿，直接输出 → CLI 显示 `90` 而非 `000090`。

### P1 — 反向适配点（改 dtype 时必须同批修，否则引入新 bug）

3. **`calculator.py:493`** `df[df["股票代码"] == int(code.zfill(6))]`
   注释写着"CSV中股票代码是int类型"——它是对当前 int64 行为的**适配**。
   一旦读入口改成 str，`str 列 == int` 永不匹配，**分红详情立刻全部查不到**。

### P2 — 冗余但无害

4. `m120_service.py:426/449/493` 的 `str(int(row["股票代码"])).zfill(6)`
   对 str 输入仍然正确（已验证 `int("000099")→99→"000099"`），只是绕。

## 目标

1. **读入口即保证类型**：所有读代码列的 CSV 入口统一 `dtype=str`，下游不再依赖"记得补偿"。
2. **同批消除反向适配**：修掉 P1，避免改了入口反而坏事。
3. **沉淀成规范**：写进 `.trellis/spec/`，后续新代码有据可依。

## 非目标

- 不删除现有 ~25 处 `astype(str).str.zfill(6)` 补偿。它们对 str 列**幂等**（已验证），
  保留可作为纵深防御。强行清理会显著扩大改动面和回归风险，收益不成正比。
- 不改前端。`apps/dividend/src/lib/types.ts` 中 `code: string` 已正确，无 `Number()`/`parseInt()` 滥用。
- 不改 douyin / global-macro-fin（本次范围限定 dividend）。

## 验收标准

- [ ] `backend/dividend-select` 内所有读取含代码列 CSV 的 `pd.read_csv` 均带 `dtype`（统一常量）
- [ ] `calculator.py:493` 分红详情能正确匹配 str 代码，用前导零样例验证
- [ ] `board_loader.py` / `stock_info_service.py` 的 `.str.replace` 不再依赖 dtype 侥幸
- [ ] 现有测试全绿：`python -m pytest tests/ -v`
- [ ] 起后端实测 `/api/dividend/stocks`，抽查前导零股票（如 `000090`）的
      board / sw_industry / shareholder / financial 字段非空
- [ ] `.trellis/spec/backend/dividend-select/backend/` 新增代码类型规范文档并挂进 index

## 关键既有事实（已实测，勿重复验证）

- `pd.read_csv(dtype={...})` 对 CSV 中**不存在的列静默忽略**，不报错 → 可用单一全局常量。
- `astype(str).str.zfill(6)` 对已是 str 的列**幂等** → 加 dtype 不会破坏现存 25 处补偿。
- `helpers.load_csv_data()` **已有** `dtype` 参数且 docstring 已写明正确用法，只是调用方没都用上。

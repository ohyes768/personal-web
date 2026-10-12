# Design: 股票代码/指数代码全链路 string 化

## 一、核心契约

> **代码类字段（股票代码 / 来源指数代码 / 代码）在系统内任何位置都是 `str`，
> 且为定长 6 位、保留前导零。类型转换只允许发生在"读入口"，不允许散落在调用点。**

边界定义：

```
akshare / 阿里云 API ──┐
                      ├─→ [normalize 入口] ─→ 系统内部一律 str ─→ CSV/JSON 写盘 ─→ API(str) ─→ 前端(string)
CSV / JSON 读盘 ───────┘
```

## 二、方案选型

| 方案 | 做法 | 取舍 |
|------|------|------|
| A. 统一 dtype 常量 ✅ | 定义 `CODE_DTYPE`，所有 `read_csv` 传入 | 显式、改动局部、零新抽象层 |
| B. 包装 `read_csv_with_codes()` | 新建包装函数 | 已有 `load_csv_data`，再包一层是重复抽象 |
| C. 全列 `dtype=str` | `read_csv(dtype=str)` | ❌ 数值列一并变 str，破坏所有计算 |

**选 A**。理由：
- 已实测 pandas 对 dtype 中不存在的列**静默忽略**，所以单一常量可无差别用于所有 CSV，
  无需为每个文件维护各自的列清单。
- `helpers.load_csv_data()` 已有 `dtype` 参数，方案 A 与之天然对齐，不新增概念。

## 三、改动设计

### 3.1 新增（`src/utils/helpers.py`）

```python
# 代码类列统一按 str 读取，避免 read_csv 推断成 int64 丢前导零（"000090" → 90）。
# pandas 对 CSV 中不存在的列会静默忽略，故此常量可无差别用于所有 CSV。
CODE_DTYPE = {"股票代码": str, "来源指数代码": str, "代码": str}
```

放置位置理由：`load_csv_data` 已在此文件且其 docstring 已描述该规则，常量与之同处一地，
不新建模块，避免 import 拓扑复杂化。

### 3.2 读入口补 dtype（P0/P1 主体）

对所有裸 `pd.read_csv` 传 `dtype=CODE_DTYPE`：

| 文件:行 | 当前状态 | 处理 |
|---------|---------|------|
| `display_results.py:30` | 无 dtype 无补偿 | 补 dtype（P0，直接修显示错误） |
| `board_loader.py:46` | 无 dtype，下游 98 行有补偿 | 补 dtype |
| `board_loader.py:65` | 无 dtype，67 行 `.str` 依赖侥幸 | 补 dtype（P0，消除 AttributeError 隐患） |
| `stock_info_service.py:~43` | 同上 | 补 dtype（P0） |
| `data_reader.py:76` | 无 dtype，106 行有补偿 | 补 dtype |
| `shareholder_financial_reader.py:40,101` | 无 dtype，41/102 有补偿 | 补 dtype |
| `m120_service.py:382,424,490` | 无 dtype，用 `str(int())` 补偿 | 补 dtype |
| `helpers.py:303` (`append_csv_row`) | 无 dtype，**产生混合类型列** | 补 dtype（P0，见 3.2.1） |
| `helpers.py:341` (`load_existing_codes`) | 无 dtype，349 行有补偿 | 补 dtype |

#### 3.2.1 `append_csv_row` 的混合类型列问题（P0）

```python
df_existing = pd.read_csv(filepath, encoding="utf-8-sig")   # 代码列 → int64: 90
df_new = pd.DataFrame([row_data])                            # 代码列 → str: "000099"
df_combined = pd.concat([df_existing, df_new], ...)          # → object 混合列
df_combined.to_csv(filepath, ...)                            # 落盘: 90 和 000099 并存
```

同一列同时出现 `90` 与 `000099` 两种格式，后续任何读取、去重、merge 都会**部分失配**。
`分红详情.csv` 正是走这条写入路径——这也解释了 `calculator.py:493`
那句"CSV中股票代码是int类型"注释的由来：它是在给这个 bug 打补丁。
补 `dtype` 后 concat 两侧同为 str，落盘格式自然统一。

补偿代码（`astype(str).str.zfill(6)`）**一律保留**——已验证对 str 幂等，作纵深防御。

### 3.3 反向适配点修复（P1，必须与 3.2 同批）

**`calculator.py:493`**

```python
# 改前（适配 int64 读入）
stock_df = df[df["股票代码"] == int(code.zfill(6))]
# 改后
stock_df = df[df["股票代码"].astype(str).str.zfill(6) == str(code).zfill(6)]
```

同时 `_load_dividend_detail_from_csv` 内的 `load_csv_data("分红详情.csv", date_str)`
需传 `dtype=CODE_DTYPE`。注释"CSV中股票代码是int类型"必须一并删除，否则误导后人。

> ⚠️ 这是本次唯一"改了入口就会坏"的点。若只做 3.2 不做 3.3，
> **分红详情会立刻全部匹配失败**（str 列 == int 恒为 False）。

### 3.4 写盘侧

写盘已正确（`fetcher.py:274` 等在 `to_csv` 前 zfill）。本次不动，
仅在规范文档中固化"写盘前必须 zfill(6)"这条要求。

### 3.5 JSON 侧 — 确认无需改动

实测 `data/favorites.json`：`items[].code = '000895'`（str），`codes` 数组亦全为 str，
前导零完好。

**根因**：JSON 是自描述格式，字符串写进去读回来仍是字符串；CSV/Excel 是无类型文本格式，
类型完全靠读取方推断——**这才是问题的唯一来源**。
`alert_service.py:279` 另有 `str(...).zfill(6)` 补偿，属双保险。

因此本规范的约束边界明确为：**CSV / Excel 读入口**，JSON 与 API 层不在范围内。

## 四、风险与回滚

| 风险 | 缓解 |
|------|------|
| 遗漏某个反向适配点，改完静默失配 | 改动后全量跑 pytest + 起服务抽查前导零股票字段非空 |
| `.str` accessor 在别处也依赖 int 行为 | 已 grep 全量 `.str.` 用法，仅申万两处涉及代码列 |
| dtype 常量列名不全 | 已枚举 `data/**/*.csv` 全部含"代码"列名，确认仅 3 个 |
| merge/dict key 两侧类型不一致 | 入口统一 str 后两侧同源，此风险随之消除 |

**回滚**：改动集中在读入口与一处比较逻辑，`git revert` 单个 commit 即可完全回退，
无数据迁移、无 schema 变更、无接口契约变更。

## 五、兼容性

- **数据文件**：不改变任何 CSV/JSON 落盘格式，历史数据无需迁移。
- **API 契约**：Pydantic 模型中 `code` 本就是 `str`，对外输出不变。
- **前端**：无改动，`types.ts` 已是 `string`。

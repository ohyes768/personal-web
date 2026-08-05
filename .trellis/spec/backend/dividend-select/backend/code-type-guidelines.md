# 代码类字段类型规范（股票代码 / 指数代码）

> 适用范围：`backend/dividend-select` 全部 Python 代码。
> 建立于 2026-08-05，源于一次全链路排查（见文末 case 附录）。

---

## 核心契约

> **代码类字段（`股票代码` / `来源指数代码` / `代码`）在系统内任何位置都是
> 6 位、保留前导零的 `str`。类型转换只允许发生在"读入口"，不允许散落在调用点。**

```
akshare / 阿里云 API ──┐
                      ├─→ [读入口归一] ─→ 系统内部一律 str ─→ 写盘 ─→ API(str) ─→ 前端(string)
CSV 读盘 ──────────────┘
```

---

## 为什么只有 CSV 有这个问题

| 格式 | 是否自描述 | 风险 |
|------|-----------|------|
| CSV / Excel | ❌ 纯文本，无类型信息 | **高** — 类型完全靠读取方推断，`000090` 必被推断成 int64 的 `90` |
| JSON | ✅ 有类型 | 无 — 写 str 读回仍是 str（已实测 `favorites.json`） |
| Pydantic / API | ✅ 有声明 | 无 — `code: str` 强约束 |

**结论：约束边界就是 CSV/Excel 读入口。** 不必在 JSON、API、前端重复设防。

---

## 必守规则

### 1. 读 CSV 一律带 `dtype=CODE_DTYPE`

```python
from src.utils.helpers import CODE_DTYPE

df = pd.read_csv(path, encoding="utf-8-sig", dtype=CODE_DTYPE)
```

`CODE_DTYPE` 定义在 `src/utils/helpers.py`：

```python
CODE_DTYPE = {"股票代码": str, "来源指数代码": str, "代码": str}
```

**pandas 会静默忽略 CSV 中不存在的列**，所以这个常量可无差别用于所有 CSV，
不需要为每个文件维护各自的列清单。

`load_csv_data()` 的 `dtype` 参数**默认值已是 `CODE_DTYPE`**，直接调用即安全：

```python
df = load_csv_data("红利指数持仓汇总.csv", date_str)   # 已自动保证 str
```

### 2. 写盘前 `zfill(6)` 归一

```python
df["股票代码"] = df["股票代码"].astype(str).str.zfill(6)
df.to_csv(path, index=False, encoding="utf-8-sig")
```

上游（akshare 等）可能返回 int，也可能返回 `001220.SZ` 这类带后缀形式，写盘前必须归一。

### 3. 比较 / 字典 key / merge 两侧同形态

```python
row = df[df["股票代码"].astype(str).str.zfill(6) == str(code).zfill(6)]
```

`astype(str).str.zfill(6)` 对已是 str 的列**幂等**，可安全用作纵深防御。

---

## 禁止模式

| ❌ 禁止 | 原因 | ✅ 正确 |
|--------|------|--------|
| `pd.read_csv(p)` 读含代码列的 CSV | 前导零丢失 | 加 `dtype=CODE_DTYPE` |
| `df[df["股票代码"] == int(code)]` | str 列 == int 恒 False | 两侧都 `str().zfill(6)` |
| `df["股票代码"].str.xxx()` 在无 dtype 保障时 | int64 列无 `.str`，抛 `AttributeError` | 先保证 dtype 再用 `.str` |
| 读回后 concat 新行再写盘（无 dtype） | 同列混入 `90` 和 `000099` 两种格式 | 读入口加 dtype |
| `except Exception: return False` 吞掉类型错误 | 数据静默变空，无从排查 | 至少 `logger.error` 带原始异常 |

---

## 新增代码自检清单

- [ ] 新加的 `pd.read_csv` 是否读到了代码列？→ 加 `dtype=CODE_DTYPE`
- [ ] 新加的 `to_csv` 前是否 `zfill(6)` 归一？
- [ ] 新的比较 / dict key / merge，两侧是否同为 6 位 str？
- [ ] 新增 CSV 若引入新的代码类列名 → **同步加进 `CODE_DTYPE`**
- [ ] 改完跑一遍：`grep -rn "pd.read_csv" src/ | grep -v dtype`

---

## Case 附录：2026-08-05 全链路排查实录

### 事实基线

CSV **写盘是对的**（落盘就是 `000090`），问题全部出在读回。实测：

| CSV | 读回 dtype | 样例 |
|-----|-----------|------|
| 个股板块映射 / 股东户数 / 财务指标 / 红利持仓 | **int64** | `000090`→`90`、`002054`→`2054` |
| 个股申万行业映射 | object(str) | 侥幸，见 case 1 |

线上之所以没大面积炸，是靠散落的约 25 处 `astype(str).str.zfill(6)` 事后补偿撑着。
**这正是要消除的脆弱契约：补偿漏一处就静默出错。**

### Case 1：申万行业整体失效隐患（最隐蔽）

`board_loader.py` / `stock_info_service.py` 在无 dtype 的列上直接 `.str.replace(...)`。
当时该 CSV 恰好因含少量带 `.SZ` 后缀的行才被推断成 object，`.str` 才可用。
**一旦某季度数据全是纯数字 → int64 → `.str` 抛 `AttributeError` → 被外层
`except Exception` 吞掉 → 申万行业信息整体变空，且无任何报错。**

> 教训：`.str` accessor 能不能用，取决于 pandas 对**当期数据**的推断结果。
> 依赖"数据恰好长这样"的代码 = 定时炸弹。

### Case 2：`append_csv_row` 制造混合类型列

```python
df_existing = pd.read_csv(filepath)            # → int64: 90
df_new = pd.DataFrame([row_data])              # → str: "000099"
df_combined = pd.concat([df_existing, df_new]) # → object 混合
df_combined.to_csv(filepath)                   # 落盘: 90 与 000099 并存
```

同列并存两种格式，后续任何读取 / 去重 / merge 都会**部分失配**。

### Case 3：反向适配点——改对了上游反而会坏

`calculator.py` 原本写着：

```python
# 筛选指定股票（CSV中股票代码是int类型）
stock_df = df[df["股票代码"] == int(code.zfill(6))]
```

它不是笔误，而是在**适配 case 2 造成的 int 现状**。
如果只给读入口加 `dtype` 而不同步改这里，`str 列 == int` 恒为 False，
**分红详情会立刻全部查不到**。

> 教训：修数据类型问题时，先 `grep` 出所有"反向适配"（`int(code)`、
> 注释写着"这里是 int"之类），它们必须与入口改动**同批次**修改。

### Case 4：去重 key 形态不一致（规划阶段漏掉，实施中发现）

`_save_dividend_detail` 用 `str(row["股票代码"])` 建去重 key，读回 int 时是 `"90"`，
而比较用的是 `"000090"` → **去重永久失效，分红详情重复累积**。

> 教训：不只看"读"和"写"，还要看**中间用代码构造 key/set/map 的地方**。

### 方法论沉淀

1. **先实测再下结论**：初次勘察把大量 `zfill` 补偿判为"高危 bug"，实测发现
   `astype(str).str.zfill(6)` 能把 `90` 正确还原为 `000090`，是**有效补偿**。
   真正的问题不是"补偿无效"，而是"依赖补偿"这件事本身脆弱。
2. **改动前先跑基线**：本次 5 个测试失败、2 个收集错误全是**预先存在**的，
   `git stash` 对照跑一次才能确认"零回归"，否则容易背锅或漏判。
3. **验收要端到端**：构造含前导零的样本数据跑真实 API，确认
   `code` / 申万 / 股东户数全链路正确，比只看单元测试可靠。

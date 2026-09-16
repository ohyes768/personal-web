# Design: DR001 定时落库（对齐 DR007）

## 数据源契约

`GET https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv`
（与 DR007 同一 URL、同 headers/UA/Referer、同 requests Session+Retry 配置）

实测行结构（2026-09-15，与 prr-md.json 当日值交叉验证）：

```
2026-09-15,,,,,,1.4266,1.4244,1.4169
^^^^^^^^^^  ^^^^^ ^^^^^ ^^^^^
date        DR001 DR007 DR014   ← index 6/7/8
```

- `dr001_service.parse_csv` 取 `cols[6]`（DR001 加权利率，单位 %），要求 `len(cols) >= 9` 且可转 float，否则跳过该行（含历史上可能的 8 列老格式行——不猜测列位）。
- 已知风险与对策：dr007_service docstring 里的 8 列老注释与实测 9 列不符（其取 index 7 恰好新旧格式都命中 DR007）。DR001 的解析以实测 9 列为准并在 docstring 记录；若货币网改列位，两服务同源同坏，可在同一处修复。

## 模块改动（镜像 DR007 现有实现）

| 文件 | 改动 |
|---|---|
| `src/services/dr001_service.py` | 重写：`DR001_CSV_URL`（同 URL）、session/retry 同 DR007、`parse_csv(csv_text)` 取 index 6 → `["date","dr001"]` 升序去重、`fetch_history(start,end)` / `fetch_latest(start,end)`（async）。删除 prr-md.json / `fetch_json` / `extract_dr001` / `fetch_today` / `_normalize_date` / POST 相关（含 `_TARGET_PRODUCT` 等常量）。 |
| `src/services/data_service.py` | ① `files["dr001"] = self.data_dir / "dr001.csv"`；② 新增 `save_dr001_data(df)`（镜像 `save_dr007_data`：空 df 建表、`["date","dr001"]` 校验、按 date 去重 keep last、升序写盘）；③ `load_dr001(path=None)` 改为读 dr001.csv（镜像 `load_dr007`），删除内部 asyncio/prr-md 实时拉取。`get_last_date("dr001")` 经 `files` 字典自动生效，无需改。 |
| `src/models.py` | 新增 `DR001Data(date, value=None)`、`DR001UpdateData(dr001: DR001Data)`，紧跟 DR007 版之后。 |
| `src/api/routes.py` | 新增 `POST /update/dr001`（镜像 `update_dr007` 全流程：`_is_updating` 锁 → `_compute_incremental_start(data_service,"dr001",...)` → `fetch_latest` → `save_dr001_data` → `DR001UpdateData` 响应；空区间返回「已是最新」）。`/update/dr007` docstring 补一行：同文件亦含 DR001/DR014 列，DR001 由 `/update/dr001` 入库。 |
| `src/scheduler/scheduler.json` | `a_share_daily.targets` 在 `/update/dr007` 后加 `"/update/dr001"`；description → 「A 股收盘后顺序更新中债/DR001/DR007/北向/成交额/换手率/融资余额」。 |
| `src/services/daily_snapshot_service.py` | **零改动**（loader 名 `load_dr001` 不变，实现内部切换）。 |

## 不改的部分（边界）

- `query_data_by_tab` / 对比页 rates tab（DR001 不进对比页）。
- `_DAILY_INDICATORS`、前端 `DAILY_GROUPS`/`INDICATOR_LABELS`（key 与展示不变）。
- prr-md.json 不保留任何代码路径（`monetary-policy-skill` 侧不受影响——那是独立实现）。

## 数据流（改造后）

```
scheduler a_share_daily (16:30, 交易日)
  → POST /update/dr001 ─┐
  → POST /update/dr007 ─┤ 各自 GET 同一 prrr-chrt.csv
                        ↓ parse_csv 取各自列
              dr001.csv / dr007.csv（合并去重升序）
                        ↓
GET /api/daily-snapshot → load_dr001/load_dr007 读 CSV → asof 取值 + 回退
```

## 兼容与回滚

- dr001.csv 首次不存在：`load_dr001` 返回空 → 页面显示「—」（与现状一致，无破坏）；首次 `/update/dr001` 从 `historical_start_date` 全量回补。
- 回滚：revert 提交即可；dr001.csv 多余文件无副作用（无人读）。

## 测试设计

- `tests/test_dr001.py` 重写（模板：`test_dr007.py`）：
  - `parse_csv`：真实 9 列格式样本（多行、去重、升序）；`len(cols)<9` 行跳过（含 8 列老格式行、空行）；index 6 非数字跳过；空输入返回空 DataFrame 保留列结构。
  - `fetch_history` / `fetch_latest`：mock `fetch_csv_text`，验证区间筛选与空结果。
  - `DataService.save_dr001_data/load_dr001` 往返（合并去重、空文件建表）——组织方式参照 test_dr007.py 对 save/load 的既有测法。
- `tests/test_daily_snapshot.py`：确认其对 load_dr001 的既有 mock/断言在新实现下仍通过（它引用 dr001，跑通即可，必要时最小适配）。
- 全量 `pytest tests/` 回归。
- 端到端（验收用，本机）：临时起 uvicorn 或直接脚本调 `DR001Service().fetch_latest(historical_start, today)` + `save_dr001_data` → `load_dr001()` 非空且最新行 = prr-chrt.csv 最新 DR001 值。

## Wrong vs Correct

- Wrong：为「消除误解」把 DR001 塞进 `/update/dr007` 内部顺便落库——端点名与行为不符，误解加深。
- Correct：镜像 DR007 独立端点 `/update/dr001`，同源不同列，docstring 互相引用说明。

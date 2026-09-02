# 债基/股基 tab 宇宙彻底隔离

## Goal

债基 tab（`/funds`）与股票 tab（`/funds/stock`）只展示各自 yaml 名单中的基金，互不泄漏。用户在任一 tab 看到的列表、导出、统计数字，都必须等于该 tab 的配置宇宙 ∩ 库内 `is_active`。

## Background

第一阶段股票 tab（已归档 `09-02-stock-fund-select-tab`）把配置、前端路由、refresh 函数拆成两套，但查询层仍共用一张 `funds` 表，且成员判定不一致：

| 表面 | 债基 | 股票 | 实际是否隔离 |
|---|---|---|---|
| yaml | `config/funds.yaml`（31 只） | `config/funds_stock.yaml`（143 只） | 是 |
| 前端 | `/funds` → `fundApi.screen` | `/funds/stock` → `stockApi.screen` | 是 |
| refresh | `refresh_configured_funds_sync` | `refresh_stock_funds_sync` | 是（写入同一张表） |
| 列表查询 | `FilterService.screen()`：`is_active=True`，不限名单 | `screen_stock()`：`fund_type LIKE 股票型/QDII/混合型`，不限名单 | **否** |

两条泄漏路径（已核对代码）：

1. **债基 tab 看到股票基金**：`screen()` 只看 `is_active`（`filter_service.py:56`）。股票 refresh 把 143 只 upsert 进同一张表且 `is_active=True`，债基列表把它们一并返回。
2. **股票 tab 看到债基名单里的混合/QDII**：`screen_stock()` 用 `fund_type` 启发式（`filter_service.py:113-124`），不用 `funds_stock.yaml`。债基 31 只里本来就有混合/QDII，会漏进股票 tab。

`/stats` 与 `/stock/stats` 同样分别按「全表 is_active」和 `fund_type` 计数，数字也会混。CSV 走同一套 `screen` / `screen_stock`，列表修了导出就跟着修。

成员判定的产品真相源是 yaml 名单，不是 `fund_type`。债基宇宙含混合/QDII；股票宇宙也含偏股混合。用类型猜成员，两边都会错。

## Requirements

1. **债基宇宙**：`GET /api/funds/screen`、`GET /api/funds/export/csv`、`GET /api/funds/stats` 的成员集合 = `funds.yaml` 代码 ∩ `is_active=True`。不得再用「库内全部活跃基金」。
2. **股票宇宙**：`GET /api/funds/stock/screen`、`GET /api/funds/stock/export/csv`、`GET /api/funds/stock/stats` 的成员集合 = `funds_stock.yaml` 代码 ∩ `is_active=True`。不得再用 `fund_type LIKE` 作为成员谓词。`fund_type` 仍可作为展示字段。
3. **交叉泄漏为零**：债基 yaml 中的代码不得出现在股票 screen 结果；股票 yaml 中的代码不得出现在债基 screen 结果。两份 yaml 当前无交集；若未来出现交集，同一代码允许同时属于两个宇宙，各自列表都展示它。
4. **清盘仍排除**：`is_active=False` 即使在 yaml 里也不进列表。
5. **现有四维筛选与排序不变**：`min_age` / `min_size_yi` / `max_dd_3y` / `min_mgr_exp` 以及各 sort 字段行为保持，只是先切宇宙再筛。
6. **详情不按宇宙 404**：`GET /api/funds/{code}` 与 `GET /api/funds/stock/{code}` 仍按 code 查库；库里有就返回。列表隔离后对比抽屉选不中对方宇宙。
7. **测试覆盖交叉泄漏**：库内同时存在债基 yaml 代码、股票 yaml 代码、以及两边都不在的活跃基金时，`screen()` 只返回债基宇宙，`screen_stock()` 只返回股票宇宙。现有 `test_filter_service.py` / `test_stock_filter_service.py` / `test_api.py` 在注入测试宇宙后仍过。

## Constraints

1. **不改 yaml 名单内容**（不增删 `funds.yaml` / `funds_stock.yaml` 里的代码）。
2. **不拆表、不加 `universe` 列、不做 alembic 迁移**。表继续共用，宇宙边界在查询层。
3. **不动 phase2-A**（`benchmark_fetcher` / `risk_free_fetcher` / `fund_benchmark` 表）。该 task 仍独立 `in_progress`。
4. **不改前端路由或 tab UI**。前端已经打到两套 API；修后端查询即可。
5. **不改 refresh 拉数路径**。两边 refresh 已经读各自 yaml；本次只修读路径。
6. **单测可注入宇宙代码列表**，不得让 `test_filter_service` 去读真实 `funds.yaml`（夹具代码是 `000001` 等，不在生产名单里）。

## Out of Scope

- 详情接口跨宇宙 404（决策 A）
- `RefreshRun` 最近一次刷新记录在债基/股票 status 之间串台（两边共用一张进度表）
- 前端对比抽屉、筛选默认值、列展示差异
- 把债基名单改成「纯债券型」或把股票名单改成「纯股票型」

## Decisions

| # | 决策 | 选择 | 依据 |
|---|---|---|---|
| 1 | 成员判定 | yaml 代码集合 ∩ `is_active`；股票 tab 去掉 `fund_type LIKE` | yaml 才是两个宇宙的真相源；两边名单都含混合/QDII |
| 2 | 隔离落点 | 查询层，不改 schema | 表共用可接受；加列/拆表超出本次缺陷 |
| 3 | 详情接口 | 仍按 code 查库，不按宇宙 404 | 列表隔离后对比抽屉没有跨宇宙入口 |
| 4 | 测试宇宙 | `screen` / `screen_stock` 可注入 codes；生产默认读 yaml | 夹具代码不在生产名单，不能绑死真实 yaml |

## Acceptance Criteria

- [x] 库内同时有债基 yaml 代码、股票 yaml 代码、以及两边都不在的活跃基金时：`screen()` 结果代码 ⊆ 债基 yaml；`screen_stock()` 结果代码 ⊆ 股票 yaml
- [x] 债基 yaml 里的混合型 / QDII 仍出现在债基 tab
- [x] 股票 yaml 里的混合型仍出现在股票 tab
- [x] `is_active=False` 即使在 yaml 中也不出现
- [x] `/api/funds/stats.total` 等于债基 yaml ∩ is_active 的数量；`/api/funds/stock/stats.total` 等于股票 yaml ∩ is_active 的数量
- [x] CSV 导出与对应 screen 成员集合一致
- [x] `GET /api/funds/{code}` 对股票 yaml 中的 code 仍 200（不因宇宙 404）
- [x] 现有 `pytest tests/ -v` 全过；新增交叉泄漏用例失败会拦住回归
- [x] 前端无需改动即可在两个 tab 看到隔离后的列表

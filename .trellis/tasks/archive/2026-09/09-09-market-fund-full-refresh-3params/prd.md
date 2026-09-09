# market fund full refresh: 3 用户参数 + 净值新鲜度后端固定 + 前端 UI

## 大白话

`discovery-stock/full/refresh` 端点当前接 3 个预筛参数（`min_ret_1y / min_ret_3y / max_nav_stale_days`），都是 L1 业绩字段。
09-09 探索后改用三阶段预筛机制：
1. **预筛 1**（L0 已有 mgr_*）：用 `mgr_experience_years` 缩 universe
2. **L1 rankhandler**：拉业绩
3. **预筛 2**（L1 已有 ret_* / nav_date）：用 `ret_3y` 缩 universe
4. **L2 size_yi**：补齐 size / age
5. **预筛 3**（L2 已有 size_yi）：用 `size_yi` 缩 universe
6. **L3 / L4 / L5**：跑剩下的小 universe

UI 上**只暴露 3 个用户参数**：`min_ret_3y / min_size_yi / min_mgr_exp`。
`max_nav_stale_days` 后端固定 = 14 天（不暴露给用户）。
`min_ret_1y / exclude_qdii` 暂不接（简化 MVP）。

## 用户视角

前端「全量刷新」按钮旁展开一个表单：

```
┌─ 全量刷新预筛 ─────────────────────┐
│ 经理从业 ≥ [__] 年                 │
│ 近 3 年涨 ≥ [__] %                │
│ 规模 ≥ [__] 亿                     │
│                                     │
│         [开始全量刷新]              │
└─────────────────────────────────────┘
```

跑完后，预筛字段同步到左侧筛选面板并**灰色 disabled**。

## Requirements

### R1 后端：`/api/funds/discovery-{stock,bond}/full/refresh` 参数收敛

**新参数**（全部 Optional）：
- `min_ret_3y: float | None` — 近 3 年涨跌幅 ≥ X%
- `min_size_yi: float | None` — 规模 ≥ Y 亿
- `min_mgr_exp: float | None` — 经理从业 ≥ W 年

**移除**：
- ~~`min_ret_1y`~~ — 简化 MVP
- ~~`max_nav_stale_days`~~ — 改为代码内常量
- ~~`exclude_qdii`~~ — 简化 MVP

**后端常量**：
```python
# src/services/market_full_pipeline.py
MAX_NAV_STALE_DAYS = 14  # 净值日距今 ≤ 14 天（A 股工作日 5 天/周 + 节假日 buffer）
```

### R2 流水线：`refresh_market_full_sync` 三段预筛

```python
def refresh_market_full_sync(
    min_mgr_exp: float | None = None,        # 预筛 1
    min_ret_3y: float | None = None,         # 预筛 2
    min_size_yi: float | None = None,        # 预筛 3
    preset_task_id: str | None = None,
) -> dict:
    # 预筛 1：全 universe 用 mgr_experience_years
    codes_all = _load_all_active(min_mgr_exp=min_mgr_exp)  # 4454 → ~3500

    # L1 rankhandler
    refresh_market_rank(codes_all)  # 50 秒

    # 预筛 2：L1 业绩字段 + max_nav_stale_days（常量）
    codes_l1 = _load_after_l1(
        codes_all,
        min_ret_3y=min_ret_3y,
        max_nav_stale_days=MAX_NAV_STALE_DAYS,
    )  # ~1573

    # L2 size_yi
    fetch_size(codes_l1)  # 10 分钟
    refresh_size(rows)

    # 预筛 3：size_yi
    codes_final = _load_after_size(codes_l1, min_size_yi=min_size_yi)  # ~1500

    # L3 / L4 / L5
    ...
```

### R3 前端：表单 + RefreshStatusPopover

**3 输入框**：
- 经理从业 ≥ [__] 年（绑定 `min_mgr_exp`）
- 近 3 年涨 ≥ [__] %（绑定 `min_ret_3y`）
- 规模 ≥ [__] 亿（绑定 `min_size_yi`）

**disabled 同步**：refresh 完成后，预筛字段同步到左侧筛选面板并 disabled。

### R4 测试

**后端**：
- `test_market_full_pipeline.py`：验证 `_load_after_l1` / `_load_after_size` / `_load_all_active` 三段预筛的 SQL 正确性
- mock `refresh_market_rank` / `fetch_size` / `refresh_size`，验证函数参数透传

**前端**：
- `RefreshStatusPopover.test.tsx`：3 输入框 + 提交按钮

## Acceptance Criteria

- [ ] **AC1** 后端 `/full/refresh` 端点只接受 `min_ret_3y / min_size_yi / min_mgr_exp` 三个参数
- [ ] **AC2** `MAX_NAV_STALE_DAYS = 14` 是模块级常量，端点不接受这个参数
- [ ] **AC3** 流水线 `_load_after_l1` 使用 `MAX_NAV_STALE_DAYS` 常量（不是 query 参数）
- [ ] **AC4** 前端表单有 3 个输入框，文案「经理从业 / 近 3 年涨 / 规模」
- [ ] **AC5** 前端调用 `/full/refresh` 时透传 3 个参数
- [ ] **AC6** refresh 完成后，预筛字段同步到左侧筛选面板并 disabled（已存在于设计文档）
- [ ] **AC7** 跑一次端到端：stock 4454 只 + `min_ret_3y=20 / min_size_yi=5 / min_mgr_exp=5`，看 universe 缩到多少

## Out of Scope

- ❌ `min_ret_1y` 预筛（隐含在 ret_3y 里）
- ❌ `exclude_qdii` toggle
- ❌ 基金类型筛选（market_types）
- ❌ 调度任务（用户明确：先做手动）

## Notes

- 字段名透传：前端 `min_ret_3y / min_size_yi / min_mgr_exp` → 后端 query 参数同名
- SQL 拼接：跟现有 `_load_market_universe` 风格一致（`if min_xxx is not None: q = q.where(...)`）
- 后端常量变更要测试：`MAX_NAV_STALE_DAYS = 14` 默认值应该跟原 query 参数默认值一致

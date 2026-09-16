# Implement: DR001 定时落库（对齐 DR007）

按序执行，每步含验证；模板参照 = `src/services/dr007_service.py`、`tests/test_dr007.py`、`routes.py` `update_dr007`（约 2773-2845 行）。

## 步骤

1. **重写 `src/services/dr001_service.py`**
   - 保留：module docstring 风格、`setup_logger`、session/Retry 构造（allowed_methods GET/HEAD）。
   - `DR001_CSV_URL` = 同 prr-chrt.csv URL；`parse_csv` 取 `cols[6]`（`len(cols)>=9`、float 可转，否则跳行）；`fetch_history`/`fetch_latest` async 镜像 DR007。
   - 删除 prr-md.json/POST/`extract_dr001`/`fetch_today`/`_normalize_date`/`DR001_REFERER`/`DR001_JSON_URL` 等全部旧件。
   - 验证：`PYTHONPATH=. ./.venv/Scripts/python.exe -c "from src.services.dr001_service import DR001Service"` 可导入；grep 无 `prr-md|extract_dr001|fetch_today` 残留于 src/。

2. **`src/services/data_service.py`**
   - `files["dr001"]`；`save_dr001_data`（镜像 444-481 行）；`load_dr001` 改读 CSV（镜像 483-496 行），删实时拉取（498-513 行旧实现）。
   - 验证：临时脚本 save→load 往返一致。

3. **`src/models.py`**：`DR001Data`/`DR001UpdateData`（127-137 行 DR007 版之后）。

4. **`src/api/routes.py`**：新增 `POST /update/dr001`（镜像 2773-2845 行，schema 换 DR001 版，`_compute_incremental_start(data_service,"dr001",...)`）；`/update/dr007` docstring 补同源说明一行。
   - 验证：app 可导入（`python -c "from src.main import app"`）。

5. **`src/scheduler/scheduler.json`**：targets 加 `/update/dr001`（dr007 之后），description 更新。
   - 验证：`python -c "import json;json.load(open('src/scheduler/scheduler.json',encoding='utf-8'))"`。

6. **重写 `tests/test_dr001.py`**（模板 `test_dr007.py`）：parse_csv 边界（真实 9 列样本/短行/老格式 8 列行/非数字/空输入/去重排序）、fetch 区间（mock `fetch_csv_text`）、save/load 往返；确认 `tests/test_daily_snapshot.py` 仍通过（其对 load_dr001 的既有 mock 如引用 fetch_today 需最小适配）。

7. **`docs/api.md`**：接口清单加 `POST /api/macro/update/dr001`（编号顺延，描述「增量更新 DR001 数据（与 DR007 同源 prr-chrt.csv，取 DR001 列）」）。

## 全量验证（最后一轮必跑）

```bash
cd backend/macro
./.venv/Scripts/python.exe -m pytest tests/ -v        # 全量回归
grep -rn "prr-md\|extract_dr001\|fetch_today" src/    # 应无生产残留
```

端到端（真实网络，脚本内完成，不提交）：
`DR001Service().fetch_latest(start, end)` → `save_dr001_data` → `load_dr001()` 最新行值与 prr-chrt.csv 最新 DR001 值一致（start=historical_start_date 首次回补场景）。

## 回滚点

- 单提交交付，revert 即回滚；dr001.csv 为新增文件，无历史覆盖风险。

## 提交（主会话执行）

- `feat(macro): DR001 改定时落库对齐 DR007 设计`（含 docs 与测试；spec 由主会话随后续 trellis-update-spec 提交）。

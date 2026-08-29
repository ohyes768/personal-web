# 执行计划：BaoStock 两市成交额/换手率

前置：任务 `task.py start` 后才可动代码。

## 步骤

1. 依赖落盘
   - `pyproject.toml` dependencies 加 `baostock>=0.9.0`
   - 验证：`.venv/Scripts/python.exe -c "import baostock"`（venv 已装，确认声明一致）

2. 新建 `src/services/baostock_service.py`（按 design.md 接口）
   - 验证：`python -m pytest tests/test_baostock_service.py -v`（先写测试，RED→GREEN）

3. 写 `tests/test_baostock_service.py`（mock baostock，按 design.md 用例 1-4）
   - 验证：`python -m pytest tests/test_baostock_service.py -v` 通过

4. 路由切换 `update_volume` / `update_turnover` → `get_baostock_service()`
   - 验证：`python -m pytest tests/ -v`（除已删除的旧测试外全部通过）

5. 新增 `POST /update/volume-turnover/history` 回补端点
   - 验证：本地起服务 `curl -X POST '.../api/macro/update/volume-turnover/history'`，
     检查响应行数

6. 删除孤儿：`volume_service.py`、`turnover_service.py`、`test_volume.py`、`test_turnover.py`
   - 验证：`grep -r "volume_service\|turnover_service" src/ tests/` 无残留引用；
     `python -m pytest tests/ -v` 全绿

7. 真实回补（一次性，先备份）
   - `cp data/volume.csv data/volume.csv.bak`（turnover 同）
   - 调回补端点（默认 2010-01-01 起）
   - 验证：`wc -l data/volume.csv data/turnover.csv` ≥ 3801；抽查 2026-08-28
     成交额 ≈ 21017±1%、无重复日期

8. 日常端点真实链路冒烟
   - `POST /api/macro/update/volume` 与 `/update/turnover` 各调一次，确认落库
     （若非交易日/盘前，确认回退到最近交易日且不写坏行）

9. 清理：删 `demo_baostock.py`；确认 `data/*.bak` 处置（保留或删，报告用户）

## 检查门

- 每步后：`python -m pytest tests/ -v` + 无 lint 报错（`ruff` 如项目有配置）
- 步骤 7 是数据变更（不可逆）→ 执行前向用户确认备份就位
- 收尾：3.3 spec 更新（BaoStock 取数约定）→ 3.4 提交

## 回滚点

- 步骤 1-6：`git checkout -- <files>` / revert
- 步骤 7：`cp data/volume.csv.bak data/volume.csv`（turnover 同）

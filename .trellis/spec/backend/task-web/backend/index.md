# backend/task-web 后端规范索引

> 定时任务管理后端（FastAPI + APScheduler + SQLite）。改动本包前先过一遍。

## Pre-Development Checklist

- [ ] 涉及 `runs` 时间戳的比较/聚合/落库 → 必读 [时间戳口径契约](./naive-timestamps.md)（naive 本地串 + `db.naive_local` 归一 + 漏执行枚举上界）
- [ ] 新增只读 API → 参照 `src/api/routes.py` 现有风格：Query 校验、HTTPException(400, 中文 detail)、服务逻辑放 `src/` 独立模块（如 `schedule.py`），不堆在 routes
- [ ] 调度器行为改动 → `src/scheduler.py` 的 tick/补记逻辑有回归测试保护，改动必须补用例
- [ ] Windows 跑 pytest → 遵循 [Windows 测试环境契约](../../backend/testing-environment.md)

## Quality Check

- [ ] `uv run python -m pytest tests/ -v` 全绿
- [ ] 时间戳比较全部经过 `db.naive_local`（见 naive-timestamps.md §4）
- [ ] 前端联调：`apps/task-web` 通过 `apiGet("/api/task-web/...")` 代理，新接口先 curl 验证再接前端

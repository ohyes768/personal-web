# 执行计划:宏观定时任务与独立管理页面

前置:design.md 已定稿。以下步骤按序执行,每步带验证。

## Phase A:后端 scheduler 包

### A1. 移植基础设施文件(纯复制,改 import/路径)
- [ ] 复制 `dividend-select/src/scheduler/{cron_human,history,trading_calendar}.py`
      → `macro/src/scheduler/`;`trading_calendar` 缓存路径对齐 macro data 目录;
      logger import 改为 macro 的 `src.utils.logger`
- 验证:`python -c "from src.scheduler.cron_human import cron_to_human"` 无报错

### A2. 移植并适配 manager.py
- [ ] 复制 `manager.py`,删 `get_holdings_codes`;`_run_job_wrapper` 透传 `items`;
      config/history 路径默认值指向 `data/scheduler/`;时区/单worker/探活逻辑原样保留
- 验证:`python -c "from src.scheduler.manager import SchedulerManager"` 无报错

### A3. 编写 jobs.py 组执行器 + scheduler.json
- [ ] `run_group(ctx, job_id)`:按 design 1.3 实现,`JOB_TARGETS = {"run_group": run_group}`
- [ ] `scheduler.json`:按 design 1.2 的 2 个分组任务
- 验证:`python -c "import json; json.load(open('src/scheduler/scheduler.json'))"`

### A4. 单测(tests/test_scheduler_jobs.py 等)
- [ ] run_group:全成功→success / 部分失败→partial / 全失败→failed /
      非交易日→skipped(mock httpx 响应与 is_trading_day)
- 验证:`python -m pytest tests/test_scheduler_jobs.py -v` 全绿(先红后绿:先写测试)

### A5. routes.py + main.py 集成 + 依赖
- [ ] 复制 scheduler routes(prefix 与 macro 现有挂载方式对齐);
      main.py startup/shutdown 挂 scheduler,`app.state.scheduler`;pyproject 加 apscheduler
- 验证:`uvicorn src.main:app --port 8094` 启动日志显示"注册 2 个任务、scheduler 启动完成";
      `curl localhost:8094/api/scheduler/jobs` 返回 2 个 job;
      `POST .../jobs/a_share_daily/run` 后 `GET .../runs` 有记录(含 items)

## Phase B:前端管理页

### B1. 类型与 API 封装
- [ ] `lib/modules/scheduler/types.ts`:SchedulerJob / SchedulerJobRun / RunItem
- [ ] `lib/modules/scheduler/api.ts`:schedulerApi.listJobs/setEnabled/runNow/getRuns
      (走 api-client direct mode,路径 `/api/macro/scheduler/*`)

### B2. 管理页面
- [ ] `modules/scheduler/page.tsx` + components(JobCard/RunsHistory/ItemTable):
      按 design 2.2;启停乐观更新+失败回滚;立即执行→延时刷新历史;防连点
- [ ] `app/scheduler/page.tsx` re-export
- 验证:`pnpm build` 通过;dev 打开 `/macro/scheduler` 页面渲染正常

### B3. 主页悬浮入口
- [ ] `modules/economic/page.tsx` 右下角固定齿轮按钮 → `Link href="/scheduler"`
- 验证:主页可见按钮,点击跳转管理页

## Phase C:联调与收尾

- [ ] start-macro-dev.bat 起前后端,页面完整点一遍:
      启停(关掉后 next_run_time 消失)、立即执行(历史出现新记录+子明细)、历史展开
- [ ] 全量测试:`python -m pytest tests/ -v` + 前端 `pnpm build`
- [ ] 确认 dividend-select 代码零改动(`git status` 不含该目录)
- [ ] trellis-check → spec 更新 → commit

## 回滚点

- Phase A 结束:后端独立可回滚(git revert 后端提交即可,不影响前端)
- Phase B 结束:前端页面无入口依赖也可独立回滚(FAB 是唯一接触点)

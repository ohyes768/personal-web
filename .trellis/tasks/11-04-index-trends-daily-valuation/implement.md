# 实施计划

## 前置
- [x] 用户批准最终规划，task.py start（status → in_progress）。
- [x] 读 trellis-before-dev 与后端相关 spec（index / valuation-contract / weekly-pipeline）。
- [x] 核对当前未提交改动，避免覆盖其他任务文件。

## 顺序
1. [x] 为每日目标日、休市跳过、日历异常、18:30/19:00缓存与重试行为补脱网测试。
2. [x] valuation_service.py 调整页面日期选择；为所有采集入口实现并发保护并测试缓存重查，保持显式周报日期规则。
3. [x] config.py、scheduler.py 增加独立cron/job与手动触发、查询、生命周期验证；main.py 解耦 daily_job 并接入独立回调。
4. [x] 验证 routes.py、report_service.py 的启动/手动/报告入口兼容和历史报告日期上限；仅必要时修改代码。
5. [x] docker-compose.nas.yml 透传配置；README、valuation-contract.md 同步每日口径；检查 CurrentTab.tsx 文案，仅按需调整。
6. [x] 执行 trellis-check，记录实际命令和限制；更新spec与任务验收记录，再按项目收尾流程处理。

## 验证
- `cd backend/index-trends && uv run pytest -q` → **237 passed**（脱网；覆盖日期、缓存/失败/滞后重试、Token、供应商解析、报告快照/幂等、调度生命周期与并发）。
- `cd apps/index-trends && ./node_modules/.bin/tsc --noEmit` → 通过；`npm run build` → 通过；
  `node --experimental-strip-types --test lib/candleData.test.ts` → 9 passed。
- compose结构检查仅输出校验结果（env key 列表），不打印展开后的敏感环境值。
- 真实环境验证需部署后的18:30任务/实际日期/周报快照证据；无证据则保持AC6未完成，避免输出Token。

## 风险与回滚
重点文件：valuation_service.py（每日/周报日期边界）、scheduler.py/main.py（重叠任务与关闭）、report_service.py（历史报告）。失败不覆盖成功缓存、不得使用未来记录、不得重复发送。
回滚此次代码与cron配置；无破坏性DB迁移，保留缓存与已发送快照。

## 实施偏差记录
- `expected_last_complete_week` 换成 `expected_last_session`（复用既有数据层helper，回看窗口逐级缩短避开日历覆盖起点）。
- `valuation_fetch_meta` 的时间戳改由估值服务注入（`at=`参数），让冷却判定与业务时钟同轴；store 其他调用方不变。
- `ReportScheduler.shutdown()` 改为幂等（未 start 或重复关闭不再抛 SchedulerNotRunningError）。
- 失败标记按目标日隔离（`_failed_for_target`）：旧失败不再抹掉新目标日的状态。

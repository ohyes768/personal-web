# 执行计划：GitHub 克隆后台任务化

前置：阅读顺序 implement.jsonl → prd.md → design.md。基线：master
（含第一阶段日志/预检代码）；当前会话分支 `fix/skill-manager-scan-timeout-ux`
（3 个未推送提交：预检错误码、前端计时器、launch.json 修复）——本任务在其上
继续，或合并后另起分支，开工时按当时状态定。

## Task 1：流式 git 执行器（RED→GREEN）

- [ ] 抓样：本地 `git clone --progress --depth 1 <fixture>` 到管道，把 stderr
  原始字节（含 `\r`）存为测试夹具字符串。
- [ ] 单测（test_git_cache.py）：
  - `GitProgress` 解析 receiving/resolving/negotiating 三类行，含残尾缓冲；
  - `_run_git_streaming` 正常完成返回 stdout、回调按序触发；
  - timeout 触发 `GitTimeoutError`（fixture 用 `git clone` 指向会长时间输出
    的本地脚本仓库不可行 → 用 monkeypatch Popen 为慢速假进程，或以
    `_REACHABILITY_TIMEOUT_SECONDS` 量级的小超时 + 真实大仓库不可取，
    采用假 Popen 进程输出进度后 sleep，触发超时 kill）；
  - 非零退出拼 `GitOperationError`（stderr 完整）。
- [ ] 实现 `_run_git_streaming` + `GitProgress`（读线程 + `proc.wait(remaining)`）。
- [ ] `scan()` / `ensure_cached()` 增加 `on_progress` 透传，clone 走 streaming。
- 验证：`python -m pytest backend/skill-manager/tests/test_git_cache.py -q` 绿。

## Task 2：TaskManager（RED→GREEN）

- [ ] 新建 backend/skill-manager/tests/test_task_manager.py：
  - scan 任务 done → 快照 state/candidates；
  - register 任务失败（fixture remotes 指向缺失仓库）→ error.code=unreachable；
  - clone 超时（Task 1 的假 Popen 手法）→ error.code=download_timeout；
  - 密码不出现在 `repr(快照)` 与 manager 内部结构（用假长密码断言）；
  - 惰性回收：完结任务 updated_at 回拨 31 分钟后查询 → task_not_found；
  - 进度回调更新快照且同 percent 不重复推进 updated_at。
- [ ] 实现 services/task_manager.py（快照 dataclass 冻结、锁、线程分派、
  错误映射、惰性回收）。
- [ ] dependencies.py 加 `get_task_manager`。
- 验证：`python -m pytest backend/skill-manager/tests/test_task_manager.py -q` 绿。

## Task 3：API 契约改造（RED→GREEN）

- [ ] models.py：`AsyncTaskCreatedResponse`、`TaskSnapshot`（含 candidates）。
- [ ] test_api.py 改造：
  - 扫描不存在仓库：仍同步 400 unreachable（AC1）；
  - 扫描可达仓库：202 `{task_id}` → 轮询 200 running → done → candidates
    与旧同步版断言一致（fixture 秒级完成，轮询间隔测试内 0.1s）；
  - 登记错密码：401 且无任务创建；对密码：202 → done → 列表可见（AC5 断言
    快照无密码）；
  - clone：202 → done；task_not_found 404；
  - test_deployment_files 既有 2 项失败维持现状（另行任务）。
- [ ] routes.py 三个 POST 改造 + 新增 GET `/github/tasks/{task_id}`；
  main.py lifespan 接 TaskManager 与启动清理。
- 验证：`python -m pytest backend/skill-manager/tests/ -q`（预期仅 2 项既有
  部署测试失败）。

## Task 4：半成品缓存根治 + 启动清理

- [ ] test_git_cache.py：clone 中途失败（假 Popen）→ `.tmp` 无残留、
  正式目录不存在；目标已存在时不覆盖（弃 tmp 分支）。
- [ ] test_main 或并入 test_api：预置 `state/scan/x` 与 `.tmp/y` 残留 →
  调 `cleanup_stale_workspaces` → 目录清空（AC8）。
- [ ] 实现 ensure_cached 临时目录 + rename 分支、cleanup_stale_workspaces、
  lifespan 接入。
- 验证：定向单测绿；全量绿（同 Task 3 例外）。

## Task 5：前端轮询 UI

- [ ] lib/types.ts + lib/api.ts：`TaskSnapshot`、start/poll 函数；
  移除旧同步响应解析。
- [ ] RegisterGithubDialog：扫描任务化（进度/计时回退/关闭停轮询/错误展示）。
- [ ] 新组件 TaskProgressDialog；page.tsx 的 performRegister / performClone
  接入；成功 notice 文案不变。
- 验证：`pnpm exec tsc --noEmit && pnpm lint`；
  preview E2E（launch.json 已修好）：不存在仓库→unreachable 文案；
  ohyes768/skills→202/进度/候选列表（AC7）；截图留证。

## Task 6：收尾

- [ ] 后端全量 + 前端检查最后一遍（AC4）。
- [ ] docs/skill-manager-nas-setup.md 若提及同步行为则补一段"克隆为后台
  任务，服务重启会丢进行中任务"；nginx 零改动确认。
- [ ] spec 更新（trellis-update-spec）：把"git --progress 用 \r 分隔、
  管道读取须手工切行"与"预览启动器参数含空格引号会被拆分"沉淀进
  .trellis/spec/ 对应文档。
- [ ] 提交（feat/fix 拆分：后端任务化、前端轮询、文档），推送，建 PR；
  PR 描述附验收清单勾选结果与 E2E 截图。

## 回滚点

- 每个 Task 一个 commit；Task 1-2 纯增量可独立 revert；
- Task 3 是前后端契约切换点，与 Task 5 必须同 PR 发布；
- 回滚 = revert 整个分支（无数据迁移）。

## 审查门

- Task 3 完成后暂停自审一遍错误映射与密码边界（对照 design §2/§5）；
- 全部完成后跑 trellis-check（spec 合规 + 全量验证）再提交 PR。

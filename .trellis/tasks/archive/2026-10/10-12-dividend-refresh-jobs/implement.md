# 实施计划（已完成本地实现与验收）

用户于 2026-10-12 明确要求规划并完成实施；使用 Codex inline 模式，不派发子代理，不提交或部署。

## 实施结果
- [x] 阅读适用股票代码、季度口径、M120 快照、筛选、调度生命周期及 Windows 测试规范。
- [x] `services/refresh_jobs.py`：后台线程、同类互斥、进度计数、持久化、重启中断与有限关闭等待。
- [x] `utils/atomic_file.py`：同目录临时文件与原子替换；接入 M120 合并和财务批次保存。
- [x] `api/routes.py`：刷新返回 202、最新任务/详情查询、保留 force/节流/股票池选择并校验代码。
- [x] `m120_service.py` / `financial_fetcher.py`：逐股进度；M120 限流留下未处理数并可重试。
- [x] `FinancialReader.read_csv(strict=True)`：写入链路禁止用空表降级覆盖不可读旧缓存。
- [x] scheduler 启动后轮询终态、碰撞跳过、记录真实成功/失败/未处理计数。
- [x] `useRefreshJobs.ts` / `RefreshJobProgress.tsx`：刷新页面恢复、关闭抽屉继续、断网恢复、失败强制重试。
- [x] 完成后刷新状态、主表/技术数据和已应用的筛选条件，保留未应用输入。
- [x] 添加管理器/API/采集器/调度与浏览器回归；更新 `refresh-jobs-contract.md`。

详细证据见 `verification.md`。线上日志核查与部署后冒烟留给部署步骤，未改变 nginx 超时。

## 原定执行顺序

1. 核对现场：读取 nginx 生效配置和错误日志，定位504请求、耗时和后端执行情况。检查同目录任务正在修改的代码；保留 M120 跨周修复，协调 scheduler shutdown 任务。
2. 阅读 Trellis 后端代码类型、M120 snapshot、财务季度与筛选契约，以及 Windows 测试临时目录规范；前端实施前补读适用指南。
3. 写失败测试：后台采集超过60秒仍能快速受理、同类互斥、计数一致、原子保存、重启中断。通过可控阻塞/时钟模拟替代真实等60秒。
4. 实现 RefreshJobManager、持久化和生命周期；添加线程安全进度回调和采集/保存错误分类。保持同步服务方法既有调用兼容。
5. 提取 M120/financial 原业务逻辑到可测试的同步作业函数；刷新路由改202，新增任务查询；原股票范围与force/90天节流测试仍须通过。
6. 同步改 scheduler/jobs.py：异步等待真正终态，定时/手动碰撞跳过，部分失败明确记录；不复用旧“任意200即成功”的判定。
7. 前端接入启动/轮询/页面恢复，显示进度和部分失败。处理网络中断、404任务不存在、重复受理及再次打开抽屉；按钮状态不被旧异步回调覆盖。
8. 质量检查：后端单元/API/调度集成测试，前端类型检查和浏览器测试，git diff --check。检查写入失败不显示成功、线程取消不释放仍在执行的锁。
9. 更新任务/API/spec文档，记录验证证据；经用户后续指令再提交/部署。部署后核查线上任务状态和下一次定时执行记录。

## 核心测试矩阵
- 受理/查询：长任务不阻塞、重复启动返回同一任务、未知任务404、非法范围/节流4xx。
- 进度/结果：全成功、部分失败、全失败、提前限流、写盘失败、未处理数量。
- 生命周期：关页面/刷新页面/断网恢复、服务重启中断、等待关闭超时不虚报停止。
- 数据：股票代码前导零、force更新不重复行、批次原子替换、旧数据可读、M120跨周兼容。
- 调度：200迁移兼容、202等待终态、手动碰撞跳过、等待超时不记录成功。

## 验证命令
后端在 backend/dividend-select 执行 `python -m pytest tests/test_refresh_jobs.py tests/test_refresh_jobs_api.py tests/test_scheduler_jobs.py tests/test_m120_rollover.py tests/test_financial_fetcher.py tests/test_screening_financial_status.py -q --basetemp=F:/personal-projects/personal-web/.tmp/pytest-dividend-refresh-jobs`（新增测试文件由实施步骤创建）。

前端在 apps/dividend 执行项目已有类型检查与 Playwright 命令；实施前读取 package.json 确认具体脚本，禁止编造不存在的验证结果。

## 高风险改动与边界
routes.py、main.py、m120_service.py 与其他任务工作区可能重叠；不回滚他人改动。scheduler/jobs.py 必须和202接口一起迁移。前端 api.ts/hooks.ts 同步发布。nginx仅用于证据核查或应急配置，不以加大超时替代后台方案。

## 进入实施的条件
规划文档已完成，服务重启策略已获用户确认。任务保持 planning；用户要求开始实施后再激活，加载 trellis-before-dev。若使用子代理，届时补充真实 implement/check JSONL 上下文；本次不派发子代理。

# 实施计划

当前为 planning，本轮只完成规划文件，不启动实施。

## 1. 测量与定位（R5/R6）

- [ ] 抓用户环境瀑布，区分首次/再次访问，记录关键资源、请求依赖和渲染完成。
- [ ] 固定 NAS 数据和并发模型，冷/热各至少 30 次，输出 p50/p95、响应大小、错误率。
- [ ] profile stocks/M120 分步成本，不触发采集或真实推送。

## 2. 精确查询与快照（R2/R4）

- [ ] 读取 trellis-before-dev 及相关 spec，检查子模块最新改动和测试布局。
- [ ] 为更新失效、新季度、文件替换、缺失后补齐及并发构建建立回归用例。
- [ ] 实现有界只读快照和代码索引，扩展 codes 查询并测试参数组合、缺失代码与前导零。
- [ ] 验证主表/股东/财务/M120/现价依赖完整，坏文件不发布错误空快照。

## 3. 计算隔离（R3）

- [ ] 搜索 get_stocks 内部调用者，提取共享服务并选定线程池边界。
- [ ] 验证并发请求、缓存失效、构建去重、事件循环延迟及刷新后可见性。
- [ ] 保留单 worker，回归刷新互斥、调度生命周期。

## 4. 前端按需加载（R1/R4）

- [ ] 根据 Tab 启用数据请求，监控只获取目标股票；现价独立于财务和 M120。
- [ ] 合并重复状态请求，保留在跑任务发现、完成后更新与跨 Tab 收藏同步。
- [ ] 浏览器回归 alerts 深链接、全量/筛选切换、fav=1、旧 watchlist、阈值外收藏、缺主表/M120、失败降级和竞态。

## 5. 验证与交付（R1–R6）

- [ ] 在 backend/dividend-select 下用 `uv run pytest --basetemp=.pytest-tmp` 运行相关及全量测试；Windows/WSL 不共享 basetemp。
- [ ] 在 apps/dividend 下运行 `npx tsc --noEmit`、`npm run build` 和相关 Playwright。先确认现有 next lint 与 Next 15 的兼容性，不把不可执行命令记为通过。
- [ ] 同数据复测性能预算，对比 JSON 字段/数值/排序/时间，记录真实改善和公网剩余限制。
- [ ] 运行 Trellis 质量检查，将缓存失效与性能契约更新到 spec。
- [ ] 获得部署授权后上线，只读复测；异常按前后端独立改动回滚。

## 启动前评审

本任务为一个跨层交付，暂不拆子任务。PRD 性能预算是拟定目标，不能将单次样本当 p95。与现有评级队列任务并存，实施前确认最新代码，避免覆盖其他工作。

若采用子代理工作流，启动前补齐真实 implement.jsonl/check.jsonl 条目，至少涵盖 research/baseline.md，以及 dividend 的 refresh-jobs-contract.md、screening-watchlist-contract.md、code-type-guidelines.md、financial-quarterly-contract.md。规划阶段不启动代理或 task.py start。

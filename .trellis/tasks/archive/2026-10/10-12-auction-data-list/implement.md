# 执行计划

1. 用户要求实施后再task.py start；先读取trellis-before-dev及法拍、小区准入、跨层复用和Windows测试契约，检查并行改动。
2. 先写失败测试：保留未关联、映射即时生效、组合筛选分页、累计计数、非法配置/参数、缺日期排序与历史去重回归。
3. 实现共享关联解析及列表查询扩展，保持存储和旧参数兼容。
4. 实现列表类型、组件、加载/重试/筛选/分页，补价格语义、缺值、状态、计数及安全链接测试。
5. 新增导航、地图定位与成功刷新联动，调整命中条数文案。
6. 验证真实累计记录、定位、桌面及390px、错误重试及快速切筛选；无需额外全量采集。
7. 全范围质量检查并保存verification.md，对照PRD记录结果，判断规格更新；不自行提交推送。

## 验证命令
- backend/housing-map：.venv/Scripts/python.exe -m pytest --basetemp=.pytest-tmp-auction-list，先目标测试再完整测试；并行任务导致失败须具体记录。
- apps/housing-map：node --test tests/auction-history.test.cjs及新增列表测试；pnpm lint；pnpm exec tsc --noEmit；pnpm build。
- git diff --check，检查本任务变更，保留其他工作流改动。

## 当前状态
仅完成规划，状态planning。实现文件预期包含auction_routes.py、auction_history.py、page.tsx、列表组件/类型/样式及对应测试；不得覆盖租金任务的最新改动。

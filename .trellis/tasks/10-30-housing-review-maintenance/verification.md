# 验证记录（2026-10-30）

## 三状态转换补充
- TDD：后端新增6例先因缺少动作/API失败，前端新增操作矩阵先因缺少组件失败；实现后通过。
- 后端相关11个套件215 passed（准入、流水线、目录、位置、用途、租金范围）；独立F盘basetemp。新增catalog过滤/统计断言后6例再验证通过。两个既有Starlette/anyio弃用警告。
- 前端全量184 passed；pnpm lint、pnpm exec tsc --noEmit、pnpm build通过。受限环境首次Turbopack CSS子进程失败，允许启动子进程后构建通过；最终按钮换行调整后再次构建通过。
- 真实CatalogTable与最终编译CSS的隔离预览，在1440桌面及390手机检查；截图review-transitions-desktop.png/review-transitions-mobile.png。修正操作组不换行后，按钮在窄列/手机中正常排列。此检查不是线上操作。
- 新动作在原SQLite准入事务内写决策和事件，旧source/position/rental/auction内容不迁移。原工作区其他改动保留；本轮未提交、推送、部署或修改线上状态。

- 回退：29a667e revert 04e0380；0130b32 股息率提交保留；无 reset 或强推。
- 测试先红后绿：新增两项测试分别发现审核仍有五个按钮、缺少主工作区导航；实现后相关47项及前端全量177项测试通过。
- pnpm lint、pnpm exec tsc --noEmit、pnpm build 均退出0。首次沙箱 build 因 Turbopack CSS 子进程提前退出失败，正常进程权限重跑构建成功；构建自动变更 next-env.d.ts 已还原。
- 浏览器使用已有 localhost:3007 dev 服务，所有 /api/map 请求拦截为测试响应，不触发业务数据写入或真实采集。验证待处理状态、地点操作筛选、主 Tab 切换、法拍事项选择与列表、租金来源列表及回到收录审核。
- 手机390×844页面 scrollWidth=390，无横向溢出；截图 maintenance-mobile.png。桌面截图 review-desktop.png 展示导航与审核筛选（截图时列表处于刷新状态）。
- 跨页入口只读核对：initialSource=laipai 仍初始化 auctions；focusPosition 仍 setMode(admitted)，主工作区由 mode 派生，未增加独立导航状态。
- Impeccable 检查仅报告 globals.css 既有规则（原 tab 边框、旧卡片及网格背景）；本次新增样式未引入这些规则，保留原界面视觉约定。
- git diff --check 通过；新实现未提交/未推送/未部署。原有未跟踪 housing-rental-matching-speed 任务未修改。当前任务保留 in_progress 待审阅和提交，不运行自动归档提交。

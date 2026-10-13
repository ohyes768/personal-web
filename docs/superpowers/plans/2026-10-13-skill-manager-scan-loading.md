# GitHub 扫描 loading 实施计划

**Goal:** 点击扫描立即反馈，请求与后台扫描期间防止重复提交，失败后允许重试。

**Architecture:** 保留现有 202 + 任务轮询接口。在 RegisterGithubDialog 增加请求提交状态和同步重复点击保护，复用现有阶段、进度与计时展示。清除上一轮任务与选择，轮询失败退出 loading。

**Tech Stack:** React 19、TypeScript、Tailwind、Vitest。

用户已确认：提交时转圈并显示“准备扫描”；后台阶段显示进度、已用时；请求/轮询失败恢复按钮。后端性能调整不在本次范围内。

- [x] 用组件状态测试验证请求未返回时的 loading、重复点击保护、成功衔接轮询、请求失败恢复及轮询失败恢复。
- [x] 运行新增测试，确认现有实现不能满足上述行为。
- [x] 修改 `apps/skill-manager/src/components/RegisterGithubDialog.tsx`，请求前置提交状态、清除旧结果、显示 spinner 和阶段计时、失败释放按钮。
- [x] 运行前端测试、lint、`tsc --noEmit`，检查改动范围。
- [x] 更新前端契约，报告原因、修复和验证；不自动提交或部署。

验证：新增测试先复现 2 项失败；修复后全部 18 项测试通过，lint、tsc --noEmit、git diff --check 通过。未进行线上性能采样或部署。

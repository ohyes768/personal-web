# 验证记录

- RED：新增后端三条回归先因缺少 mode/status 失败；新增前端按钮测试先因缺少按钮失败。
- 后端完整套件：842 passed，65.69s（3 个环境/依赖 warning）。最后增强实际 DirectoryJob 转交模式的测试后，相关目录/API 套件再次验证。
- 前端关联套件：35 passed；lint 与 tsc --noEmit 通过。
- 前端完整套件：75 tests / 72 passed / 3 failed。失败位于未修改的 community-management 紧凑来源卡片旧断言，以及 rental-dashboard/rental-sources 对已不存在的 RentalRefreshButton.tsx 引用。未扩大本次范围。
- 默认 Turbopack 在沙箱内因 CSS 子进程启动失败；Webpack 沙箱内编译和类型检查通过，静态输出因 EPERM 中断。沙箱外 npx next build --webpack 完整成功，静态页全部生成。
- playwright-cli 对实际 CollectionControls 静态渲染 + 项目 CSS 做 1440px/390px 验证，两个按钮完整可见，dialog 无横向溢出。点击回调参数和禁用状态由前端测试验证；未触发真实采集请求。
- git diff --check 通过；保留原有 .claude/launch.json 改动。
- 用户已于本轮确认提交并推送；未部署，未触发真实上游采集。

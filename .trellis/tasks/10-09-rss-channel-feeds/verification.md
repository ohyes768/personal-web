# 验证记录

- 后端：在backend/rss-relay设置PYTHONPATH=.test-deps;.、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1，python -m pytest tests -q：4 passed（根代理复验1.82s）。沙箱TestClient线程挂起，提权执行通过。
- UI：node .trellis/tasks/10-09-rss-channel-feeds/ui-smoke.cjs，使用本地前后端和test-token，PASS。覆盖渠道新增、编辑、停用、恢复、独立链接channel/token、动态Python示例、手机390px无横向溢出、剪贴板拒绝后手动复制、Escape焦点恢复。浏览器无pageerror。
- 截图desktop.png/mobile.png已人工视觉检查：渠道直接复制，全部内容独立区域，移动端完整可操作。
- git diff --check通过。
- 前端最终pnpm build exit 0：编译、类型检查与静态页生成通过；pnpm exec tsc --noEmit exit 0。

## 发布边界
未修改NAS、阅读器订阅或外部推送工具；存量文章不推测频道归属。部署后推送工具需加channel字段，旧推送仍归未分类。

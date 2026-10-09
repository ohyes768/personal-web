# 验证记录

- 后端：在backend/rss-relay设置PYTHONPATH=.test-deps;.、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1，python -m pytest tests -q：4 passed（根代理复验1.82s）。沙箱TestClient线程挂起，提权执行通过。
- UI：node .trellis/tasks/10-09-rss-channel-feeds/ui-smoke.cjs，使用本地前后端和test-token，PASS。覆盖渠道新增、编辑、停用、恢复、独立链接channel/token、动态Python示例、手机390px无横向溢出、剪贴板拒绝后手动复制、Escape焦点恢复。浏览器无pageerror。
- 截图desktop.png/mobile.png已人工视觉检查：渠道直接复制，全部内容独立区域，移动端完整可操作。
- git diff --check通过。
- 前端最终pnpm build exit 0：编译、类型检查与静态页生成通过；pnpm exec tsc --noEmit exit 0。

## 发布边界
未修改NAS、阅读器订阅或外部推送工具；存量文章不推测频道归属。部署后推送工具需加channel字段，旧推送仍归未分类。

## 2026-10-09 订阅 token 构建链路修复
- 根因：deploy-nas.sh默认前端buildx直构建，rss-relay映射漏传NEXT_PUBLIC_RSS_TOKEN；compose build.args虽正确但此路径不读取。
- 修复：buildx映射从同一个RSS_RELAY_TOKEN传入NEXT_PUBLIC_RSS_TOKEN。
- 回归：scripts/tests/test_rss_build_args.py用真实构建函数及假docker执行，修复前缺少--build-arg而失败，修复后通过；bash -n通过。未连接NAS，不宣称已检查NAS根.env或线上镜像。
- 当前修复尚未提交推送、未部署。需要修复版本重新构建前端后线上才生效。

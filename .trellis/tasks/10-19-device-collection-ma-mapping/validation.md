# 本地验证记录

日期：2026-10-19（Asia/Shanghai）。

- 后端：`.venv/Scripts/python -m pytest -q --tb=short`，85 passed、1 skipped（既有符号链接权限用例），1 条现有 Starlette TestClient 弃用提示。
- 前端：`pnpm exec tsc --noEmit` 通过；`pnpm build` 通过，静态 / 页面 3.3 kB、First Load JS 106 kB。沙箱内 standalone 依赖复制出现 EPERM，改用本机受审查命令后完成构建。
- 浏览器：Playwright 使用本地真实 MP3 fixture 与 FakeMA 预览，验证生成按钮更新成功；1280×720 与 390×844 截图已检查，编号与 8/15/30 首排序正确，无布局溢出。截图在 .trellis/.runtime/device-playlist-desktop.png 和 device-playlist-mobile.png。控制台只有既有缺失 favicon 的 404。
- 独立静态审查指出：实际 album_tracks 展开曲序未校验。补两例先失败测试，改用展开曲目编号及返回顺序与文件清单核对后通过全量测试。
- 已按 trellis-check 复核事务发布、凭据不外泄、容量错误保留、旧 revision 拒绝及前后端代理契约，并补齐 package 注册和开发规范。

## 现场事实与未完成验收

NAS 只读检查：music-assistant 镜像 2.8.2，真实目录包含 1、8、18、20、91、420、1106、3000 曲等合集；两个服务的音频目录均挂到 /music。检查安装版源码确认 /api 直接返回 JSON，item_by_uri 接受 uri，filesystem_local mapping.item_id 为 relative_path。

MA 实际未认证调用返回 401，尚无 kids-catalog 可用 token；已告知用户在 MA 设置 → 个人资料 → 长期访问令牌创建，并保存 NAS /home/ohyes768/personal-web/.env。未打印或写入任何真实密钥。

本地 fixture 不等于真实 NAS 专辑匹配及播放验收。PRD 验收项保留未勾选，任务不归档。尚未部署、提交、修改音频、烧录固件或更改 HA。

## 提交前复核

用户已告知 NAS env 配置完成，并授权提交推送；未读取或提交密钥。重新执行后端全量测试（85 passed、1 skipped）与前端 TypeScript 检查均通过。真实 MA 联调及部署仍待进行。

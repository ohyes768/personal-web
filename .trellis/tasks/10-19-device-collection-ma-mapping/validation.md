# 本地验证记录

当前验收以本文最后的“目录与 MA 解耦”记录为准；下方早期 MA 匹配测试和联调记录仅保留历史背景。

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

## 2026-10-20 当月来源修正

用户明确只生成 kids 当前展示的当月合集。修复前新增测试复现历史专辑被错误纳入；修复后仅处理 albums JOIN jobs(status=done)，无已下载来源时保留旧快照且不扫 NAS。标题保留 kids 原名，跳过报告另含 folder 用于确认。独立审查发现最终来源核对与发布之间的窗口，新增先失败并发测试；改为上下文管理器持有 Catalog 写锁到发布提交（锁序 Catalog→device）后通过。

最新本地验证：后端全量 89 passed、1 skipped；TypeScript 检查通过，生产构建通过。

NAS 只读核对：当前 kids 列表 16 项，其中 done 13 项；MA 认证正常。小妃摇篮曲 8 个文件中仅 1 首关联专辑；小月姐姐 1106 首与晚安妈妈 3000 首虽已关联，MA album_tracks 实际只返回 500 首，修正错误文案显示返回数与本地数，不伪造成功映射。

尝试上传修正后的 device_collections.py 到 NAS /tmp 做隔离试跑，被自动审批拒绝：理由为未明确授权向远程 NAS 发送源代码。未绕过限制、未部署此轮修正、未修改真实音频。等待用户明确部署授权。

## 2026-10-20 目录与 MA 解耦

用户批准 web 只提供编号与专辑名称关系。生成只读取 kids 当月 done 白名单内的 NAS 正式音频，统计曲数、升序编号；移除所有 MA 关联、曲序、整张专辑匹配及联网可用性门槛。编号查询仅返回 revision、number、title、track_count；不再返回 media_type/ma_media_uri，不表示可播放性。

- 后端全量：92 passed、1 skipped；仅保留既有 Starlette TestClient 弃用提示。禁止目录与名称查询网络请求、501/1106/3000首、普通文件名、旧 targets 无效内容、失败保留、来源变化和并发发布等用例通过。
- 额外文件名回归：普通名称及上标数字前缀（非十进制曲序）均可计数，针对用例1 passed。
- 状态一致性：确定性测试先复现两次 SELECT 跨提交导致 done/旧目录混读，再以显式读事务修复并通过。
- 独立静态审查：未发现有证据支持的正确性问题，已核对 MA 解耦、旧库兼容、来源锁、完成记录、状态事务及文档一致性。
- 前端：TypeScript 检查和 `pnpm build` 通过（首页3.33 kB，First Load JS106 kB）；本轮仅更新现有组件提示文案，布局未改动。任务上下文校验、`git diff --check` 通过。
- 未继续 MA 维护，未上传 NAS 源码或部署，未修改音频、HA 或设备固件；真实播放不在本轮验收内。

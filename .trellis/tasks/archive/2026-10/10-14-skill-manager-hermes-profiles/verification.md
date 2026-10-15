# Hermes 多 profile 实施验收 — 2026-10-14

## 实施结果

已实现受控 JSON target 配置、持久安装身份 catalog、TargetResolver、legacy/API/migration/export 分类兼容、按 Skill/target 的统一计划与执行、共享仓库更新影响、动态 profile UI、精确失败重试、NAS override 示例和 Windows 双目标模拟配置。

追加 schema 前对旧运行库自动创建 `.before-hermes-profiles`；首次旧库 catalog 建立仍验证原 HERMES_SKILLS_ROOT 与 active hermes 的对应关系。有 active 台账的 ID 不得改根，未配置历史目标不恢复写权限。此次实施没有读取或修改实际 Hermes/NAS 运行库、目录或凭据，仅测试临时库与模拟页面。

## 验证命令及环境

环境：macOS，本机真实符号链接测试，无 Windows/WSL/NAS 操作。

- 后端：`UV_CACHE_DIR=/private/tmp/personal-web-uv-cache uv run pytest -q`。**257 passed，0 skipped**。全量检查含配置、catalog/旧库备份、真实双目标链接、部分冲突、精确候选重试、仓库 checkout 复用、unselected profile 更新影响、密码/幂等/过期计划与来源删除保护；原 direct-cache、export、migration 套件保留。
- 前端：`node node_modules/typescript/bin/tsc --noEmit` 与 `node node_modules/vitest/vitest.mjs run`（48 项），通过。
- 前端 lint：给 NODE_PATH 添加当前 node_modules/.pnpm/*/node_modules 后运行现有 ESLint，通过。本机 pnpm wrapper 会尝试重装并因非 TTY 停止，因此使用同一已安装依赖直接执行；未改 package.json/锁文件/依赖版本。
- 前端 build：同一 NODE_PATH 环境运行 `node node_modules/next/dist/bin/next build`，生产编译、内置 lint、类型验证、静态页面及 standalone 构建通过。
- `git diff --check` 通过。
- 后端仅有已安装 Starlette/AnyIO 的弃用提示，不影响执行。

## 浏览器模拟验收

运行生产构建 + 本机内存模拟 API，使用 Codex 浏览器交互验证：默认 profile 的 alpha 已安装；切 ohyes768 后显示未安装并更新 URL target 与实际目录；刷新 URL 恢复当前目标；安装 gamma 弹窗默认只勾当前 profile，勾第二目标生成两条预览；模拟一成功一冲突，重试勾选和预览仅剩失败目标，重试后显示安装成功及当前目标徽章。

截图：`/Users/tang/.codex/visualizations/2026/10/14/01a13a68-557f-70e1-9989-49606e7ce1bd/skill-manager-profile-retry.png`。

模拟服务与验收页已关闭。该结果证明 UI 交互，不代表真实 Hermes 发现或执行能力。

## AC 对照

| AC | 证据 |
| --- | --- |
| AC1 | two/three catalog、配置歧义拒绝、缺失目标独立降级及 ZIP 回归 |
| AC2 | ProfileViews 单目标状态/board 测试、浏览器切换/目录/默认目标验证 |
| AC3 | 真实双链、部分冲突仅失败 pair 重试、candidate registry upsert 一次 |
| AC4 | 原 plan TTL/任务丢失 UI 回归、幂等提交、source/root/link/config/impact 指纹变化拒绝 |
| AC5 | 全 profile 影响列表、共享仓库 checkout 一次、未选择目标读取新版、独立 unpublish |
| AC6 | 旧 catalog 不重定向、旧库备份、未配置 active 目标保护源、profile 不进 export，原 OpenClaw 退役回归 |
| AC7 | invalid/empty targets 无副作用、ordinary occupant、symlink 逃逸原 publisher 回归、目录替换/密码边界 |
| AC8 | backend/frontend checks、生产 build 与浏览器模拟完成；真实 Hermes 部署验收留待后续 |

## Spec 审阅

新增 `.trellis/spec/backend/skill-manager/backend/profiles.md` 的七段可执行契约；同步 cache/frontend/export guides 和索引，去除固定集合分类与单目标描述。新知识：目录授权与持久目标身份必须分开；确认指纹分 source/pair；候选精确重试复用仓库/path 身份并传 per-candidate targets。

## 待用户操作

工作成果可提交；项目 workflow 3.4 要求一次提交计划确认，尚未 commit/push/archive。真实 NAS 部署与 Hermes 实际发现/读取验证按后续部署指令进行。

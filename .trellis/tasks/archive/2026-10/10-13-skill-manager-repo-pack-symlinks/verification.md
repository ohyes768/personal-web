# 实施与验证记录（2026-10-13）

## 已实现

- GitHub 一仓库一卡片、只读库存；整包添加/安装/转换/更新/卸载/删除。
- 每目标一条包根软链，共用稳定 checkout；更新不再 staging/切换版本链接。
- OpenClaw 分组 extraDirs 适配；所有权、配置备份和按包撤销，保留用户配置。
- 旧登记归并、部分安装明确转换、持久恢复日志和引用保护；旧强制 checkout API 禁止改动包仓库。
- 脏树/分叉拒绝更新、候选兼容检查、仓库锁内重新读状态、缓存修复同步 OpenClaw 分组。
- 更新 spec 与 NAS 配置挂载 override、Nginx /api/github-packs 路由。

## Windows 验证

- 最终相关后端回归：31 passed / 3 requires_symlink skipped，273.65s。
  覆盖包域、迁移、HTTP 边界及旧 staging 目录重命名回归。
- 配置/部署/发现适配回归：20 passed。
- 最后三处审查修复针对性验证：6 passed（锁后读取、未完成转换保护、修复分组同步）。
- 原 GitCacheService 回归：43 passed。
- 前端：TypeScript、ESLint、8 suites / 27 tests 通过。
  ESLint 使用现有 pnpm package store 的 NODE_PATH 解决本机依赖解析。
- Next build：编译、类型与静态页生成完成；standalone 打包因 Windows
  EPERM symlink 失败，内嵌 ESLint 另有本机 react-hooks 依赖链接解析问题。
  不宣称部署镜像已构建通过。
- git diff --check 已清理本任务空白问题；未修改其他并行任务内容。

早先全量 Windows：208 passed / 16 skipped / 4 failed。
三个失败源于旧部署静态断言落后于现有 Compose/静态首页，已修正并在20项
配置测试中通过；旧 staging Windows rename 偶发权限失败在最终相关回归通过。
依用户要求收敛验证，不再重跑14分钟全量。

## 实机发现证据与边界

NAS 既有 Hermes loader 在临时单根软链中发现22项。OpenClaw 2026.4.11
rootSymlink=0、groupThroughSymlink=22，证明需分组配置适配；没有改变生产配置、
现有安装或运行服务。此证据验证发现机制，不冒充新代码已在 NAS 部署验收。

用户明确要求仅 Windows，已停止 WSL。新业务3项真实软链测试因当前Windows
权限跳过，已记录，不称其通过。

私有代码验证包上传 NAS 被自动审批拒绝（缺少具体上传授权），未绕过。
仅本地源码与部署配置已准备；没有提交、推送或部署 NAS。

## 审查结论

已修正：旧源启动搬移断链、候选校验落地太晚、构造恢复阻断服务、
迁移反复写覆盖/删除复活、包 ID 碰撞、大小写缓存重复、配置全局回滚覆盖、
锁前旧状态写回、缓存修复遗漏分组同步、未完成恢复时破坏性操作。

代码交付可审查，生产部署/实装验证待后续明确执行；任务保留 in_progress，
不因未提交代码而自动归档。

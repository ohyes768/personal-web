# 实施计划

状态 in_progress；2026-10-14 用户批准实施，功能与验证已完成，等待提交确认。两个部署挂载是已单独授权的前置改动，保留并与任务成果一同验证。

1. [x] 读取 trellis-before-dev、profile contracts 和四份 skill-manager guides；检查当前 dirty state，保留 Codex template hashes/.pnpm-store，确认已授权的 compose/doc 前置差异。
2. [x] 添加 profiles 父根 Settings/受控候选发现，覆盖缺失根、单目录名、逃逸/重定向、源/cache/state 重叠、目录权限与规范根重复。前端不接受任意路径。
3. [x] 添加 install_target 操作配置列、一次性 env 导入、revision/tombstone 和目标配置审计；备份旧库，验证 default/有效旧 named 身份和安装保留、历史 catalog 不获授权、重复启动不覆盖网页名称/复活删除、同目录恢复身份。
4. [x] TargetResolver 改为每次读取当前配置，Publisher/旧 API/列表/安装计划/启动迁移使用同一授权解析；维持 unmanaged/offline active rows 源删除保护。
5. [x] 实现候选 GET 和目标 POST/PATCH/DELETE；复用密码守卫，operation_lock + BEGIN IMMEDIATE 检查 config revision、active 台账，验证 default保护/并发创建/安装与删除竞态/错误密码无副作用。
6. [x] 实现 `view=install-targets`、默认只读行、候选选择+名称、新增/改名/删除密码确认、active阻止与跳转下架。刷新动态名单，处理旧URL/加载错误/旧响应；安装对话框不能静默换目标。
7. [x] 注入 profiles 授权 env，更新 Windows dev 模拟路径和部署说明；保留源缓存同路径可达性、不创建实际 Hermes 环境/凭据、不部署 NAS。
8. [x] 更新 profile code-spec 与 guide 指针，写 verification.md，对照 AC1–AC8；完成最终整体 review 后提交计划等待一次确认。

## 验证

backend/skill-manager：`uv run pytest`；新增目标CRUD/候选/迁移测试，真实 symlink 安装后验证active删除拒绝、独立下架后软删除只移除配置、删后env不复活、恢复沿用ID、并发无孤立active行。原多profile共享缓存/精确重试、export、direct-cache、OpenClaw退役套件通过。

apps/skill-manager：`pnpm test`、`pnpm exec tsc --noEmit`、`pnpm lint`、`pnpm build`。本机pnpm wrapper依赖解析若仍有问题，可用已有依赖的同一工具直接执行并记录，不改锁文件绕过。

浏览器模拟：默认只读、网页连续新增两profile后无需重启即出现在弹窗、改名、active删除引导、下架后删、加载失败/未知target及ZIP回归。真实Hermes验收另列，不以模拟API代替。

部署配置：独立临时 env 运行 `docker compose config --format json` 验证默认与override两挂载同路径、rw、不自动mkdir，以及profiles授权env一致；不读真实.env。

## 风险与回退点

- DB迁移和启动seed：不能给历史路径授权，不能删除配置后被env复活；失败回滚事务并保留备份。
- Resolver/config fingerprint：检查每个旧消费者，配置变化拒绝旧计划。
- target删除：active包括异常/不可访问台账，不能因文件系统观察解除引用。
- 部署父根：可见范围已获用户确认，应用仅处理严格skills路径；规范根变化不可自动搬旧链。
- 所有实现仅在最新最终规划批准后 `task.py start`；开发完成后提交/push与实际部署按各自授权执行。

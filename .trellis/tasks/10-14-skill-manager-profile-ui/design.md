# 界面维护安装目标 — 技术设计

## 架构与授权

保留同路径父挂载、本地 Publisher 原子软链操作、共享 registry/cache、operation_lock 和已有安装后台任务。新增持久目标配置服务，由 TargetResolver 每次查询当前 DB 操作状态与版本；移除其在构造时长期缓存可写 targets 的行为。Settings 仅负责固定默认根、profiles 父根与源/cache/state 授权，不让 SQLite 中任意 last_root 授予写入权。

新增 SKILL_MANAGER_HERMES_PROFILES_ROOT，compose 从 HERMES_PROFILES_HOST_PATH 注入。授权根保持实际原始配置路径和首次规范路径；后续解析重定向拒绝。默认 HERMES_SKILLS_ROOT 仍与现有根一致；它变更且有 active 记录时保持已有阻止逻辑。未配置父根的旧部署继续支持默认和当时明确配置且冻结根匹配的 legacy named 安装（这些 named 不能网页编辑），profile 管理入口报告未就绪，不扩大到其他父目录。

候选发现只列 profiles 父根的直接普通子目录，检查 `<profile>/skills`；不读取目录中的 auth/config/.env，不递归扫描其他内容。每次新增/执行复验名字是单个目录分量、skills 规范路径严格在授权根内，拒绝路径逃逸/根替换及 profile/skills 链重定向。请求只传 profile_name 和显示名称。将目录状态与是否已登记分开返回，缺目录等候选可诊断但不能保存。

## 持久模型与升级

在 install_target 增加操作配置列：managed（是否由受信任配置/网页登记）、removed_at（软删除）、config_revision（单调递增）。既有 last_root 继续保存冻结的规范技能根，profile_name/name 保持。默认与历史不能按 managed 缺省值自动获得新权限；增量迁移置历史 unmanaged。

一次性 `install_targets_ui_v1` 迁移在 BEGIN IMMEDIATE 中只导入当时 Settings 明确配置的、符合当前授权根的目标，保留其 ID/名称/根/安装与审计。默认 hermes 沿原 HERMES_SKILLS_ROOT 验证；named 目标必须对应 profiles 直接子目录的 skills。仅历史 catalog、未配置目标及越出新授权根的旧 named 记录保留为不可操作，不恢复授权、不迁移文件。

迁移前备份 SQLite；迁移标记一旦写入，后续启动 env JSON 不再覆盖、补种或复活网页已删除的 named 目标。保持旧 env 配置只用于首次受信任导入和诊断。默认根仍由 Settings 控制，default 行只读。父根/默认根更换不自动迁移 frozen last_root；不匹配目标明确不可用并保留 active 保护。

新 ID 由服务端从 profile 名称派生合法 slug，冲突时加稳定短摘要，沿用已经导入/已删除同目录目标的 ID；保证 ID/profile identity 和规范根的唯一性，客户端不选择 ID。仅 name 可 PATCH；profile/path/provider 不可改。DELETE 软删除 managed 配置，保留 deployment/历史和身份；重新新增相同目录可恢复旧行并递增 revision。

## API

- 扩展 `GET /api/skills/install-targets`：保留旧字段，增加 editable、deletable、removed、active_installation_count、config_revision。管理页可展示不可操作历史，现有选择器只使用未删除配置；保留旧 URL 的异常提示。
- `GET /api/skills/install-targets/profiles`：返回发现的 profile_name、skills_path、available、unavailable_reason、existing_target_id；父根未配置/不可用时明确状态，不假装空目录。
- `POST /api/skills/install-targets`：`{profile_name,name,password}`；创建或恢复身份，重复 live 目标 409 target_exists。
- `PATCH /api/skills/install-targets/{id}`：`{name,expected_revision,password}`；仅改名，版本冲突 409 target_changed，拒绝未知字段/null。
- `DELETE /api/skills/install-targets/{id}`：`{expected_revision,password}`；default 400 reserved_target，有 active 409 target_in_use（含数量/成员），过期版本 409 target_changed，成功软删除。

路由放在 skill_id 动态路径前，返回结构不包含密码。新增 target_config_history 或专用 append-only 审计表，记录 target/action/time/old/new public metadata/result，避免用要求 Skill ID 的安装审计伪造占位 Skill。受限事务错误应通过既有顶层 code/message 格式返回。

## 并发与计划

新增/改名/删除、安装、旧 publish/unpublish 和启动迁移共享 operation_lock。DB mutation 用短连接事务复验 expected_revision 与 active rows。DELETE 检查所有 active 安装，不因链接缺失或 root 不可达而放行；不读取/删 profile 磁盘内容。正常下架按既有单目标流程完成后解除 active 保护。

计划目标 fingerprint 包含 config_revision、managed/removed、profile/name/frozen root 和当前目录/link identity；提交和每项 publish 前重读配置，删除/改名/恢复或父路径变化导致 stale_plan。不能把 DB 的新状态自动吸收进已确认计划。旧 Publisher 和 API 都通过同一个 resolver，防止旧入口继续写软删除目标。源码删除保护继续包含 unmanaged/offline active rows。

## UI

`view=install-targets` 新一级导航，不改原 `view=targets` 导出入口。页面列出默认固定行、有效 profile 卡片和异常/已移除历史摘要。卡片显示显示名/profile/真实目录/可用原因/active 数量。新增表单从候选列表选择 profile，显示自动计算目录并填写显示名；保存或改名用管理密码确认，不在浏览器持久化密码。

删除弹窗明确“只移除安装目标配置，不删除环境和 Skill”。active>0 时禁用确认并链接到 `view=board&target=<id>`；后端仍作最终冲突检查。默认行隐藏编辑/删除。无 active 的历史 removed 行保留只读摘要，提供通过新增同 profile 恢复的说明。

CRUD 后刷新目标管理、当前名单和选择器；不静默把已经打开的安装弹窗移往另一目标。被删除当前 URL target 保留异常与可选列表，由用户自己切换。候选/管理加载失败提供重试并禁止提交，过期响应忽略。既有 export 页面、仅登记、安装组合键、失败精确重试与合集完整下载保持。

## 部署与回退

已有 compose 两挂载作为本任务前置，进一步只增加后端 profiles 授权 env 和 dev 模拟父目录。Windows dev 模拟 `targets/profiles/<profile>/skills`，保留已有 legacy 数据，不搬运旧链。README 写首次升级、网页维护、不可用诊断、profile 外旧目录处理与 active 删除保护。

先备份旧库并上线支持新 schema 的后端，再前端；回退后端需恢复旧数据库/旧 env 管理方式，不能让旧启动 sync 覆盖网页配置。软删除不删文件，回退不会自动撤销链接。实际 NAS 部署或对 profile 运行时的发现/读取验证需另行授权，不在本轮规划操作。

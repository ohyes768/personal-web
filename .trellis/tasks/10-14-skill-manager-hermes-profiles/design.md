# Hermes 多 profile 技术设计

## 1. 架构与边界

保留 registry、共享源库/GitHub cache、Publisher、InstallManager 和 SQLite。新增 TargetResolver，作为目标分类、元数据、可用性和写入目录解析的唯一入口。Publisher、API 列表、安装指纹和启动迁移均使用它，消除散落的 `settings.hermes_skills_root` 与静态 `LINK_TARGET_IDS` 判断。

```text
服务目标配置 ──> TargetResolver ──> 安装目标清单 / 受控目录解析
                         │
registry + shared cache ─┼─> InstallManager（来源一次准备、skill × target 计划）
                         │                      │
                         └─────────────────> Publisher（逐目标原子链接替换）
                                                │
                                  deployment / deployment_history
```

配置是当前可写目录的唯一依据；数据库保留目标身份和历史元数据，不从旧数据库路径恢复未配置目标的写权限。服务继续单 worker，复用已有 operation_lock，首版不引入新的调度器或外部队列。

## 2. 目标 ID 与数据

- 旧目标保持 `hermes` 并对应现有根；预计为默认环境，上线前核对实际映射。若旧根实际属于某个 named profile，则按真实环境命名并保留旧 ID/路径，再为其他环境配置独立目标，不能静默转移存量链接。不迁移旧 ID 为 `hermes:default`。
- 命名 profile 采用 `hermes:profile:<slug>`，例 `hermes:profile:ohyes768`。创建独立 InstallTargetId 校验类型，禁止使用 SkillId/静态 Agent 枚举替代它。
- `slug` 是配置指定的稳定身份，profile_name 和显示名称可独立描述实际 Hermes 名称；不会通过用户请求拼接目录。
- 导出目标现有 ID 不允许冒号，因此 profile 命名空间与导出自然区分；默认 `hermes` 继续为保留 ID。
- deployment 的 `(skill_id, target)` 主键及历史 target 字段复用，无需复制 registry。新增 `install_target` 元数据表：`id, provider, profile_name, name, last_root`；provider 固定 hermes。新表不保存密码或 profile 凭据，不作为目录授权真源。
- 配置目标按 ID 更新元数据；移出配置的目标仍由 catalog 返回 `configured=false, available=false`。保留 deployment 和历史；没有配置不操作旧 last_root。
- 有 active 台账时，配置将同一 ID 改为不同规范目录必须报配置冲突；要求先恢复原配置、完成下架或走独立迁移。显示名变化不改变安装身份。已有普通配置 path 不擅自重命名 profile。

## 3. 配置与部署

新增 `SKILL_MANAGER_HERMES_TARGETS` JSON 配置列表，每项包含 `id, name, profile_name, skills_root`。示例宿主机 home 仅作占位，实际实施按用户 NAS home 替换：

```json
[
  {"id":"hermes","name":"默认环境","profile_name":"default","skills_root":"/home/user/.hermes/skills"},
  {"id":"hermes:profile:ohyes768","name":"ohyes768","profile_name":"ohyes768","skills_root":"/home/user/.hermes/profiles/ohyes768/skills"}
]
```

- 未设置新配置时，现有 `HERMES_SKILLS_ROOT` 生成唯一默认目标，保持旧部署与 dev 启动可运行。新配置设置时以列表为准；旧变量不再隐式添加目标。
- 配置为空、ID 重复、非法 ID、非绝对路径、与导出目标冲突、规范目标根重复或互相包含时启动报配置错误。源库、缓存和 state 继续沿用现有必填存在性规则。
- 已配置目标目录缺失或不可访问是目标不可用状态；不会阻止健康目标提供服务，也不自动 mkdir。写操作实际尝试仍可能因权限变化失败，不把可用性探测当作保证。
- 每次计划/执行/下架重新校验根目录及 resolve 结果；捕获规范路径和目录身份，目录被替换或符号链接重定向后要求重新预览，越出配置授权范围直接拒绝。
- 如配置了 targets_mount_root，继续校验包含关系。NAS 未设时，以显式同路径 bind mounts 限定可访问文件系统。
- compose 保留默认 skills 目录挂载，首版添加可选命名 profile skills 同路径挂载示例，完整配置通过 env JSON 注入；不把整份 `~/.hermes` 或 profiles 根挂入后端。后续更多 profile 使用 compose override 增加各自 skills 挂载，配置和挂载必须同时就绪。
- Windows dev 用 `.skill-manager-dev/targets/hermes` 和独立 `.../hermes-ohyes768` 模拟两目标，实际路径通过脚本生成；模拟路径不宣称为真实 Hermes home。

## 4. API 与计划

`GET /api/skills/install-targets` 返回配置和历史目标：`id, provider, profile_name, name, install_path, configured, available, unavailable_reason`。使用已有 `/api/skills/*` nginx 路由，无新增独立 base 路径。

统一预览支持三种互斥输入：

1. 新已登记安装：`items: [{skill_id, targets:[target_id]}]`，复用现有队列单项形状，以便精确重试失败组合。
2. 新候选安装：已有 scan_task_id/candidates 加 `target_ids`，服务分配 Skill 身份后展开组合。
3. 旧兼容：原 `skill_ids` 或未带 target_ids 的候选，目标仅为 `hermes`；默认目标不可用时明确报错，不静默转向某个 named profile。

所有目标合法性/配置状态在来源准备和任何登记副作用前校验。空目标列表不得隐式默认；无效组合、重复项去重与容量限制统一定义。建议每计划最多 100 Skill、20 目标、500 个组合，超过同步拒绝。

Plan 改为分开保存 Skill 来源状态和目标组合状态：登记快照、缓存 HEAD、确认 revision、源哈希每 Skill/仓库复用；目标根指纹、现有链接与动作按组合保存。预览返回 item.target，以及本次仓库更新可能影响的 `affected_installations`（skill/target 清单）。执行请求继续仅提交 plan_id、request_id 和本次密码，不允许临时改目标。

执行顺序：校验计划 → 每仓库准备确认版本 → 每 Skill 解析来源/一次登记 → 逐目标重新验证目标指纹和原子发布 → 逐组合记结果/审计。缓存 checkout 后更新同计划内同仓库来源指纹，不能把未预期的外部变化吸收成合法计划。

源准备失败作用于该来源的所有目标；目标冲突只影响该组合。结果含 `skill_id, target, name, registered, status, action, error`，UI key 使用组合键。重试使用失败结果生成新的 items 并重新预览，不沿用旧计划、不重试成功组合。全 unchanged 时无写入确认步骤。

旧 publish/plan/unpublish API 同步支持 InstallTargetId 并通过 resolver 查找；旧 target=hermes 继续可用。不能只升级统一安装接口而让旧路由接受静态类型或写到错误目录。

## 5. 账实核对、共享源与生命周期

link/export 分类通过已知 catalog 和目标命名空间完成。未知 `hermes:profile:*` 记录保留为不可用安装目标，不能使用「不在静态 link 集合中」推断为 export。

链接状态以当前目标目录中真实链接是否匹配受控来源为准；数据库 active 但目标缺失/移出配置/悬空时显示异常。安装时刻记录仍可保留，GitHub 列表展示直链当前 cache HEAD，而非虚构逐 profile 固定版本。

更新 GitHub 共用缓存影响同仓库所有 profile 中已安装成员；affected_installations 包含未被本次安装选中的目标。预览后影响集合变化需要重新确认；无法访问目标的 active 台账也列为可能受影响，不假定已卸载。现有 Clone 等可更新缓存的入口同样说明影响范围。

自研内容修改、Hermes 沿链接修改可写源都会被其他 profile 看到。直链不提供写入隔离，不在本任务改变源目录权限或 skill_manage 配置。规划记录此行为，实际部署验收核对运行权限。

删除 registry/缓存检查所有 install_target 的 active 台账，包括未配置目标；只能通过有授权路径的明确下架释放引用。下架删除单个目标受管链接，不递归删除目标目录或源目录。

## 6. UI

管理和安装看板增加同一个当前 profile 选择，URL 用 `target=<ID>` 保存。旧 URL 无 target 时回到 hermes；带旧 agent 参数仍按默认 Hermes 打开。未知 target 提示目标不可用并提供可用列表，不能自动把已打开的确认弹窗换目标。

管理卡片和合集统计按当前 profile；可附「已安装到 2 个 profile」摘要，但具体动作目标清楚。统一安装弹窗默认当前目标，可多选可用 profile，随后自动预览并一次密码确认；切换目标清除旧 plan/request 状态，忽略晚到预览响应。结果逐 Skill/profile 展示。

下架仅在安装看板针对当前 profile；合集全部下架保持完整已登记成员范围和逐项结果。来源 tab、搜索和合集展开与 profile 切换相互独立。安装目标是只读服务配置列表，不复用 ZIP 导出目标 CRUD 页面。

## 7. 兼容、上线与回退

升级前备份 SQLite。catalog 迁移幂等；默认 `hermes` 从现有配置登记，已有行不改 ID、revision、时间或历史。首次加入 named profile 只提供可选目标，不创建部署或链接。启动旧缓存/快照迁移遍历 resolver 已知且可用的 active link 目标，正确直链跳过，未配置目标记录可诊断问题并保留状态。

上线采用先后端兼容旧客户端、再前端启用选择的顺序。前端回退可使用旧单目标界面；后端版本回退必须恢复升级前数据库备份/旧配置，不直接让旧后端读取含 profile 记录的新库（旧代码会将其误分类为 export 或无法解析枚举）。回退管理台不会撤销已创建的 named profile 链接，需保留其源/缓存挂载并先规划后续管理方式。

## 8. 取舍

配置登记适合明确挂载和少量 profile，用户已确认；自动扫描、网页任意路径编辑与 profile 进程控制不纳入首版。保留 `hermes` ID 减少存量迁移风险；独立 catalog 只为持久身份/离线台账服务，不引入第二套路径授权。共享直链继承当前产品的版本语义，独立版本需另外设计快照模型。

# Skill Manager 外部导出目标契约

## Scope / Trigger

修改目标枚举、部署台账、ZIP 导出或列表过期检测时必读。
`models.LINK_TARGET_IDS` 为固定发布集合；导出目标配置来自 SQLite `export_target`。
前端 `lib/targets.ts` 只保留固定 link 标签；动态导出名称由页面加载并下传。
`windows-codex/windows-claude` 是一次性迁移的默认导出配置，不是完整目标集合。

## Signatures

- `GET/POST /api/export-targets` 与 `PATCH/DELETE /api/export-targets/{id}` 管理配置（免密）。
- 字段：`id,name,install_path,notes,enabled`；列表与写响应含 `deployment_count`。
- `POST /api/skills/{skill_id}/export {"target":"<export-target-id>"}` → ZIP 附件。
- `DELETE /api/skills/{skill_id}/exports/{target}` → `{skill_id,target,status:"removed"}`。
- `deployment.content_hash TEXT NOT NULL DEFAULT ''`，启动按 PRAGMA 缺列迁移。
- `TargetDeployment` 新字段：`content_hash: str`、`stale: bool`。

## Contracts

导出和清除台账免密，发布/下架密码边界不变。导出仅接受 export 目标，
不覆盖 link 发布记录。打包先取得同一内容快照，ZIP 与台账哈希严格同源。
源为自研登记目录或 GitHub 共享缓存中的登记子目录（当前 checkout）；
无网络操作，不包含 shared_paths。ZIP 无外层目录、固定时间戳，排除 `.git`
和 symlink，文件相对路径用 POSIX。哈希包含路径与字节长度，避免分隔歧义。
revision 尽力读取自研源库/缓存 HEAD，失败为空；UI 空 revision 回退短哈希。

列表仅对有非空哈希的 active export 记录计算当前内容，每 Skill 一次；
源不可用视为 stale，空哈希旧记录保持 False。export 的 link_missing 恒 False。
启动自动重发布必须跳过 export。删除登记仅被 active link 记录阻止，
成功后清理全部部署台账。清除 export 记录不访问目标文件系统。

## Validation & Error Matrix

| 输入/场景 | 结果 |
|---|---|
| export 进入 plan/publish/unpublish | 400：旧固定 Windows 目标为 invalid_target_kind；自定义 ID 被固定发布枚举拒绝（plan/publish 为 invalid_request，unpublish 为 invalid_target） |
| link 进入 export/清除 export | 400 invalid_target_kind |
| GitHub 缓存缺失导出 | 400 cache_missing_export，提示先 Clone |
| 源缺失或逃逸 | 400 source_unavailable |
| 未知 skill / target | 404 skill_not_found / 400 invalid_target |

## Good / Base / Bad Cases

- Good：导出 → 修改源 → 列表 stale=True → 再导出 stale=False。
- Base：旧库空哈希不误报；重复导出同内容产生相同 ZIP。
- Bad：export 进入 symlink 发布、账实核对或启动重发布。

## Tests Required

`tests/test_api.py` 的 export 测试覆盖离线 GitHub、自研、ZIP、台账与 stale；
`tests/test_exporting.py` 覆盖迁移、哈希、排除 `.git` 与启动跳过 export。
前端 `targets.test.ts` 验证 Windows 目标不在 LINK_TARGETS 中。

## Wrong vs Correct

Wrong：循环每条 deployment 都调用 `_target_root()` 或启动重发布。
Correct：先判断 `record.target in LINK_TARGET_IDS`，只有固定 link ID 才转 `TargetKey` 并检查/更新 symlink。

## 动态目标管理（2026-10-10）

- ID 使用 skill ID 的小写字母/数字/短横线约束，最长 63 字符，创建后不可改；`openclaw/hermes` 保留。名称必填（strip 后 1–100），说明最多 500，备注最多 2000 字符。PATCH 禁止未知字段与显式 null。
- `state_migration/export_targets_v1` 保证两个旧 Windows 目标只初始化一次，保留旧台账，不覆盖用户修改；删除默认目标后重启不会重建。
- 目录说明与备注只是文本，不访问目录；导出内容与 ZIP 哈希规则不变。
- 删除目标在 `BEGIN IMMEDIATE` 下检查所有 deployment 行（含 removed），有行返回 409 `target_in_use`；审计行保留且不阻止删除。
- 导出在打包前查询启用状态，写台账和审计时 `record_export()` 在同一个事务再次校验存在且 enabled，防止打包期间删除/停用后写入孤立台账。PATCH 在事务内返回更新结果，避免并发删除导致响应空值。
- 停用返回 400 `target_disabled`；未知导出 ID 为 400 `invalid_target`；重复为 409 `target_exists`；保留 ID 为 400 `reserved_target`；配置不存在编辑/删除为 404 `target_not_found`。
- 停用不隐藏历史台账、不阻止清除；前端重新导出禁用。加载配置失败显示错误并禁止新导出，不能默认为空列表。
- 一级导航 `?view=targets`；导出/清除/删除 Skill 后刷新技能与目标计数。动态目标不进入发布队列、link_missing 计算或启动重发布。
- 本地 Next rewrite 与生产 Nginx 都必须代理 `/api/export-targets`（精确集合）及 `/api/export-targets/`（子路径）；NAS 上前后端更新后还须下发 Nginx 并 reload。
- 测试：API 目标 CRUD/自定义 stale/清除/发布边界，`test_targets.py` 的默认配置持久化、removed 行阻止删除与写台账前并发状态复验；前端动态选择、空列表、加载失败及停用清除渲染。

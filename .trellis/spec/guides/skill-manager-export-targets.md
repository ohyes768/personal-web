# Skill Manager 外部导出目标契约

## Scope / Trigger

修改目标枚举、部署台账、ZIP 导出或列表过期检测时必读。
`models.TARGET_KINDS` / `target_kind()` 是后端唯一分类入口；前端对应 `lib/targets.ts`。
`openclaw/hermes` 为 link；`windows-codex/windows-claude` 为 export。

## Signatures

- `POST /api/skills/{skill_id}/export {"target":"windows-codex"}` → ZIP 附件。
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
| export 进入 plan/publish/unpublish | 400 invalid_target_kind：外部目标请在卡片上导出，不走发布 |
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
Correct：先 `target_kind(TargetKey(record.target))`，仅 link 检查/更新 symlink。

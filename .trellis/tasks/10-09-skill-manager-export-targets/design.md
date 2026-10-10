# 技术设计：外部导出目标与版本台账

## 目标模型（单一事实源）

`models.py`：

```python
class TargetKey(StrEnum):
    OPENCLAW = "openclaw"
    HERMES = "hermes"
    WINDOWS_CODEX = "windows-codex"
    WINDOWS_CLAUDE = "windows-claude"

TargetKind = Literal["link", "export"]

TARGET_KINDS: dict[TargetKey, TargetKind] = {
    OPENCLAW: "link", HERMES: "link",
    WINDOWS_CODEX: "export", WINDOWS_CLAUDE: "export",
}
def target_kind(key: TargetKey) -> TargetKind  # 唯一判定入口
```

后续加新目标 = TargetKey 加成员 + TARGET_KINDS 加一行（link 型再加
settings 路径与 `_target_root` 映射）——平台可管理。前端
`lib/targets.ts` 同步一份（key/kind/label/说明文案）。

## 守卫矩阵（谁在哪里被允许）

| 流程 | link 目标 | export 目标 |
|---|---|---|
| 发布队列 / plan / publish / unpublish(下架) / 回滚 | ✓（现状） | 400 `invalid_target_kind`："外部目标请在卡片上导出，不走发布" |
| `_target_root` / Publisher symlink | ✓ | 永不触达（入口已被守卫拦截） |
| 账实核对 link_missing / cache_missing | ✓ | 不适用（跳过） |
| 导出 | 400（避免覆盖 link 发布台账） | ✓（主场景） |
| 删除 skill 级联 | active link 阻止删除，下架后清台账 | 不阻止删除登记，同时清 export 台账 |

实现：`_require_link_target(target)`（routes + publisher 入口统一调用）；
queue 模型 `QueueItemRequest.targets` 校验消息同步收紧（pydantic 层只校验
枚举，kind 校验在路由层给 400 文案）。

## DB 迁移（最小）

`deployment` 加列：`content_hash TEXT NOT NULL DEFAULT ''`。
- `_SCHEMA` 的 CREATE TABLE 同步加列（新库直建）；
- 启动迁移：`PRAGMA table_info(deployment)` 无该列则
  `ALTER TABLE deployment ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''`
  （SkillStateStore 已有启动建表入口，同处执行；旧记录 '' → 永不 stale，
  AC5）。
- `DeploymentRecord` dataclass 加字段；`current_link_target` 对 export 记录
  存 `"export"`（语义占位，列 NOT NULL）。

## 内容哈希（过期判定的唯一依据）

```
dir_hash(root) = sha256(排序文件：路径字节长度 + 相对路径 posix + 内容字节长度 + 文件字节)
```
- 排序后串接，忽略平台差异（Windows/NAS 路径分隔符统一 posix 相对路径）；
- 跟随 symlink 的内容不算（源库/缓存内无 symlink，防御性跳过非常规文件）；
- 放 `src/services/exporting.py`，同时管理内容快照、哈希和 ZIP + 单测（改一个字节 → 哈希变；
  文件改名 → 哈希变）。
- 台账写入：`content_hash = dir_hash(导出时的目录)`；过期 = 列表时
  `dir_hash(当前目录) != recorded`。
- 自研 stale 判定用**源目录**（skills_source_root/path）；GitHub 用**共享缓存
  登记子目录**（repos/owner__repo/skill.path）——与导出内容来源严格同源，保证"重新导出即
  追平"。

## 导出端点

```
POST /api/skills/{id}/export   body: {"target": TargetKey}
  → 400 cache_missing_export（GitHub 缓存缺失，提示先 Clone）
  → 400 invalid_target / 404 skill_not_found（沿用现有守卫）
  → 200 application/zip + Content-Disposition: attachment; filename="<id>-<短hash>.zip"
    副作用：upsert deployment(status="active", source_revision=rev,
            content_hash=hash, current_link_target="export",
            source_path=登记 path, published_at=now)
```

- 打包：zipfile + ZipInfo 固定 `date_time=(1980,1,1,0,0,0)`（内容寻址，不泄
  本地时间；重复导出同内容字节一致）；目录即 zip 根（无外层包裹目录，解压
  即 skill 目录内容，含 SKILL.md）。
- revision 取值：自研 = `git -C source_root rev-parse HEAD`（失败→""，尽力
  而不打断导出）；GitHub = `current_revision`（缓存 HEAD）。
- **免密**：与 check-updates 同层（只读内容 + 记台账，不碰 link 目标文件
  系统）；PRD Constraints 已声明。
- 加 `deployment_history` 一条 action="export"（复用现有审计表，不新增表）。

## 列表 stale 计算（惰性、廉价）

`list_skills` 组装卡片时：
- 有 export 记录 → `dir_hash(当前源/缓存目录)` 对比 recorded content_hash
  → `TargetDeployment` 扩展 `stale: bool`（link 目标恒 False）。
- 哈希成本：每 skill 一次目录遍历（KB~MB 级），个人规模（<100 skills）毫秒
  级，可接受；不加缓存。
- 前端 `TargetDeployment` 类型加 `stale`。

## 前端

- `lib/targets.ts`：四目标 meta（key/kind/label/描述）；`TARGET_LABEL` 迁入。
- 卡片：部署状态区在 OpenClaw/Hermes 之外显示有记录的 export 目标 chip
  （`Codex(Win) · a1b2c3d · 10-09` + stale 时黄点"源已更新，点击重新导出"）；
- 导出弹窗（新小组件 ExportDialog）：选择 codex / claude（单选）→ 确认 →
  fetch POST → blob 下载（`URL.createObjectURL` + a[download]）→ 成功后
  刷新列表 + notice「已导出「X」给 Windows Codex，台账已记录」；
- chip 上的删除（垃圾桶小图标）：确认后 DELETE 台账（文案明示"仅清除记录，
  不动本地已解压文件"）。
- 发布队列目标选择器只列 link 目标（现状 UI 已按 TARGET_LABEL 渲染，过滤
  kind=export）。

## 删除/下架语义

- 删除 skill：现有 delete 级联 `store.delete_deployments(skill_id)`（全
  target）——确认覆盖 export 记录即可，无需改。
- export 记录的"下架"= 删除记录（R5），不等于 unpublish（那是 link 专属）。

## 风险与对策

| 风险 | 对策 |
|---|---|
| QueueItem/plan 放行 export 导致 Publisher 建目录 | 入口守卫 `_require_link_target`，publisher 内部再断言一层 |
| 旧库 ALTER 失败（并发启动） | 迁移放 SkillStateStore 初始化（单线程启动段），PRAGMA 先查 |
| 大目录打包内存 | 当前按个人 MB 级 Skill 取得内存快照，ZIP 与哈希使用同一份字节，避免二次读取漂移；大目录未来改临时文件快照 |
| 哈希遍历拖慢列表 | 个人规模毫秒级；如未来变慢再加 TTL 缓存（不做，YAGNI） |

## 回滚

单分支 revert；DB 新列向后兼容（旧代码无视新列），无需数据回滚。

## 实施核对（2026-10-09）

- 导出只允许 export 目标，避免 `(skill_id,target)` 单行台账覆盖 symlink 发布记录。
- GitHub 源采用仓库共享缓存登记子目录，不采用已废弃的 cache_root/skill_id 布局。
- 导出排除 `.git` 和 symlink；哈希按路径/内容长度编码并与 ZIP 使用同一字节快照。
- 删除登记原流程没有部署台账级联，已补齐；仅 active link 阻止删除，export 不阻止。
- 无缓存或源不可用的已导出记录显示 stale，旧空哈希仍不误报。
- 启动迁移必须跳过 export，前端重新导出预选被点击记录的目标。

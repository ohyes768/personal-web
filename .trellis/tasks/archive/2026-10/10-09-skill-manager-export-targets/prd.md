# skill-manager 外部导出目标与版本台账

## Goal

把 Skill 发布管理台的"目标"统一建模为两类，平台统一管理：

- **link 型**（NAS 自有，现状不动）：OpenClaw / Hermes，发布 = symlink，内容
  永远跟随源；
- **export 型**（外部机器，新增）：Windows Codex / Claude Code，"导出"= 打包
  下载 + 台账记账一步完成；源更新后卡片自动高亮"该同步了"。

背景：Windows 本地 agent 无法使用 NAS symlink（跨机器），只能复制副本；副本
会静默过期，所以版本台账 + 过期高亮是核心闭环。**不做 Windows 端 CLI**（用户
决策：导出动作本身就长在下载里，不存在忘记记账）。

## Requirements

- R1 目标模型：`TargetKey` 扩展 `windows-codex`、`windows-claude`；新增
  `TargetKind`（`link` / `export`）映射，平台级唯一定义处。link 型 = 既有
  openclaw/hermes；export 型无宿主路径，仅台账。
- R2 边界守卫：发布计划/发布/下架等 **link 专属流程** 对 export 目标返回
  400（明确文案"外部目标用导出，不走发布"）；export 目标不参与 symlink
  发布器、不参与 plan 预览、不参与 link_missing 账实核对。
- R3 导出端点 `POST /api/skills/github` 之外新增
  `POST /api/skills/{id}/export {target}`（免密，与"浏览/检查更新免密"边界
  一致；body 仅记账，不改目标文件系统）：
  - 响应为 zip 附件（Content-Disposition），内容 = 该 skill 当前登记目录
    （自研：源库目录；GitHub：缓存当前检出目录）；
  - 同步写/覆盖台账：`deployment` 记录（status="active"、source_revision=
    当前可得的版本号、content_hash=当前目录内容哈希、current_link_target=""
    或 "export:"）；
  - 自研 skill：revision 取源库 git HEAD（不可得则空串）；GitHub skill：
    revision 取缓存 HEAD；**缓存缺失的 GitHub skill 导出 → 400 提示先 Clone**；
  - 重复导出同一目标 = 覆盖记录为新版本（这就是"同步"动作本身）。
- R4 台账与过期检测：`deployment` 表加 `content_hash` 列（启动迁移 ALTER
  TABLE，旧记录 ''=未知不过期）。列表接口对有 export 记录的卡片惰性计算
  当前哈希：不一致 → 卡片该目标位标"源已更新"（stale）；一致 → 最新。
  自研 stale 的同时若该 skill 尚未发布到任何 link 目标，不额外提示（scope
  只管 export 副本过期）。
- R5 前端：卡片部署状态区显示有记录的 export 目标位（目标名 + 版本短码 +
  时间，stale 黄点"源已更新"）；卡片操作区加"导出"图标按钮 → 弹窗选
  codex/claude → 下载 zip + 刷新列表（新记录出现）；export 记录支持删除
  （台账清除，不动本地文件，弹窗明示）。
- R6 文档：docs/skill-manager-nas-setup.md 补 export 目标说明；spec 沉淀
  目标两类模型。

## Constraints

- link 型全部既有语义零回归（发布/下架/回滚/plan/cache_missing/账实核对）。
- zip 而非 tar.gz：Windows 资源管理器原生解压（Python zipfile 标准库）。
- 打包只含 skill 登记目录内容，路径以 skill 目录为根；导出不动 NAS 目标目录。
- 密码边界不变：导出/记账免密；发布/下架仍需密码。
- Windows 开发机仅验收 API/打包/台账（symlink 流照旧 skipped），E2E 下载
  zip 可本地验证。

## Acceptance Criteria

- [ ] AC1 发布计划/发布请求带 export 目标 → 400，文案明确；link 目标全流程
      既有测试零回归。
- [ ] AC2 导出自研 skill：zip 内容 = 源库当前目录（含 SKILL.md），台账记录
      git HEAD + 目录哈希；再次导出覆盖为新哈希。
- [ ] AC3 导出 GitHub skill：缓存缺失 → 400"先 Clone"；有缓存 → zip 来自
      缓存检出目录，台账记缓存 HEAD + 哈希。
- [ ] AC4 源更新检测：导出自研后修改源目录（测试中改文件）→ 列表卡片该
      export 目标 stale=true；重新导出 → stale=false。GitHub 路径同理
      （重挂缓存内容模拟）。
- [ ] AC5 旧库迁移：无 content_hash 列的库启动后自动补列，旧记录
      hash=''（不误报 stale）。
- [ ] AC6 前端 tsc/lint/vitest 绿；导出弹窗、stale 徽章、删除记录交互完整；
      后端全量 pytest 仅既有 2 项部署漂移失败。
- [ ] AC7 密码/边界回归：发布仍需密码；导出免密可用；export 目标不出现在
      发布队列可选目标里。

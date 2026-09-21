# skill-manager 登记真源迁移 SQLite

## Goal

skill-manager 的登记真源从 skills 仓库的 `registry.json`（+ git commit）迁移为
skill-manager 自己的 SQLite 库，彻底移除登记/删除对 git 的依赖（NAS 生产环境
`git add` 报 128 的问题从根上消失）。`registry.json` 回归其原主人——skills
仓库的 4 个 sync 脚本工具链，skill-manager 不再读写它。

## Background

- 实际使用是单环境（NAS 生产），跨环境清单同步是过度设计
- registry.json 的真实消费方是 skills 仓库 scripts/ 下 4 个 sync 脚本
  （registry_loader / sync_skills / sync_github_skills / sync_github_versions），
  它们在 Windows 上按 junction 方式同步 skill，skill-manager 后来才借用此文件
- 后续规划（独立任务，非本任务）：界面编辑条目 + 手动导入/导出 registry.json

## Requirements

- R1 新增 `registry_skill` 表（既有 skill-manager.sqlite3，不建新库），作为登记真源。
- R2 登记真源相关的全部操作（列表/登记/删除/查单条）改读 DB；`commit_registry_change`
  及其两处调用点（登记、删除路由）删除；登记/删除不再产生任何 git 子进程调用。
- R3 一次性自动迁移：启动时若 `registry.json` 存在且 `registry_skill` 表为空，
  解析并全部导入（含 local 与 github 条目）；表非空则跳过（单向迁移，绝不回写、
  绝不重复导入）。损坏的 registry.json + 空表 → 启动失败并给出清晰报错。
- R4 `registry.json` 文件本身保持原样：skill-manager 的任何操作不得修改它；
  agents 字段不导入 DB（控制台不用，归 sync 工具链）。
- R5 行为契约保持：唯一性校验（重复 id、github 重复 repository+path）、tags
  排序去重、local path 边界校验（SKILL.md 存在且不逃逸源库根）、错误码与状态码
  与现状对齐（登记/删除密码契约不变）。
- R6 前端零改动（API 契约不变）。
- R7 文档同步：`docs/skill-manager-nas-setup.md` 中 registry git 提交/推送相关
  描述更新为新语义。

## Out of Scope

- 界面编辑、手动导入/导出（下一个任务）
- agents（agent 分配）数据入库
- skills 仓库侧 4 个 sync 脚本与 README 的任何改动
- GitHub clone/fetch 仍需要 git（拉代码用），不在本任务范围

## Acceptance Criteria

- [ ] 迁移：现有 registry.json（17 local + 3 github）启动后完整出现在列表接口；
      重启后不重复导入；迁移后 registry.json 文件内容与迁移前逐字节一致。
- [ ] 登记：新 GitHub skill 登记 → DB 出现行、列表可见、registry.json 文件不变、
      无 git 子进程调用（subprocess 断言）。
- [ ] 删除：登记条目删除 → DB 行消失、registry.json 不变、无 git 子进程调用；
      源目录不是 git 仓库时（模拟 NAS 128 场景）登记/删除照常成功。
- [ ] 契约：重复 id / 重复 github repository+path 被拒且状态码与现状一致；
      密码错误 401；local 条目删除 400；active 部署删除 409。
- [ ] 空表 + 无 registry.json → 空列表正常启动；空表 + 损坏 registry.json →
      启动失败报错清晰。
- [ ] `backend/skill-manager` pytest 全绿；前端不改动（lint 免跑）。

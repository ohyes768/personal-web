# 安装目标网页管理验收 — 2026-10-14

## 结果与变更边界

安装目标 CRUD、profiles/skills 候选、SQLite 一次性导入/软删除/版本与审计、live resolver、配置变化失效与安装删除并发保护、默认只读页面、现有多目标安装/下架集成、父目录挂载和授权 env、dev 双profile 模拟及部署材料已完成。

默认目录始终保留原 hermes 身份与冻结根；网页仅管理 profiles 直接子目录的 skills。已有 source/cache/ZIP/仅登记不改变。未配置父根的旧部署可沿原明确配置根使用 legacy 安装，不给新 UI 创建目标，也不从历史 last_root 恢复权限。

## 验证

- macOS 真实文件系统/软链，后端全量 pytest **275 passed，0 skipped**；目标 CRUD/部署专项测试通过；没有 Windows/WSL/NAS 测试或操作。
- 前端 52 项测试通过，TypeScript、ESLint 和 Next 生产构建通过，无代码抑制。沿本机已安装依赖直接执行 tools；lint/build 用 NODE_PATH 指向既有 .pnpm 依赖目录，不修改依赖版本/锁文件。
- 默认与 custom 两套 compose 配置使用临时虚拟 env，通过 config JSON 核对两项 source/target 同路径、rw、不自动 mkdir，以及 profiles/default 授权 env 同步；没有读取真实 .env。
- git diff --check 通过。后端只有已有 Starlette/AnyIO 弃用提示。

## 浏览器与真实测试后端联调

使用生产前端构建、只监听本机的临时 FastAPI 后端及 `/private/tmp/skill-target-ui-fixture` 受控目录，所有内容是新建的测试 Skill 和 profile 目录，密码为一次性公开测试值。

1. 默认行显示只读，无编辑/删除；发现 one/two/three 的现有 skills。
2. 网页先后新增 one 和 two，无重启即进入管理选择器与安装弹窗；已登记候选禁选。
3. 在 one 实际安装 Demo Skill，形成真实 symlink，管理行 active 数量更新为 1。
4. 点击删除被阻止，仅有进入该目标部署看板按钮；正常下架后 active 归零，方可密码确认移除配置。
5. one 的目录和 removed 部署/配置历史保留；two 改名“测试环境二”，其 profile/路径不变。
6. 实际重启测试后端并刷新浏览器，改名和已移除状态保留；浏览器无 error 日志。

截图（测试目录，非 NAS 环境）：
- `/Users/tang/.codex/visualizations/2026/10/14/01a13a68-557f-70e1-9989-49606e7ce1bd/target-ui-management.png`
- `/Users/tang/.codex/visualizations/2026/10/14/01a13a68-557f-70e1-9989-49606e7ce1bd/target-ui-delete-blocked.png`

测试后端、代理前端和浏览器页已停止。真实 NAS/Hermes 发现/执行验收尚未进行。

## AC 映射

| AC | 验证 |
| --- | --- |
| AC1 | 管理入口/selector shortcut/default 只读单元和浏览器 |
| AC2 | 浏览器连续新增 two profiles，即时安装，实际后端重启后保留 |
| AC3 | 候选缺目录/未知/路径逃逸/符号链接重定向，凭据文件不读取单测；无mkdir |
| AC4 | name-only revision mutation、重复创建冲突、restore 原 ID、env 不覆盖/复活单测 |
| AC5 | active/缺失link 仍拒删除，明确下架后只软删配置；default保护，源/目录/历史保留 |
| AC6 | 旧表备份与一次性 seed、unmanaged 不授权、原 profiles/direct-cache/export/OpenClaw 回归 |
| AC7 | 401无副作用、stale revision/plan、安装删除竞态、worker准备来源前复验；ZIP等原套件 |
| AC8 | 全量backend/frontend、类型/lint/build、真实临时backend浏览器；NAS另行部署 |

## Spec 与交付

已更新 backend profiles 七段接口/存储/错误/实例/测试契约与 frontend guide。关键知识：目录授权与 DB 身份分开，env 只 seed 一次；删除保留 tombstone；worker 取得锁后需在 checkout/登记前复验目标，不能只在请求线程检验。

未提交/push/archive，待 workflow Phase 3.4 一次提交确认。housing-map、Codex template hashes 与依赖缓存为并行/既有改动，排除本任务提交。

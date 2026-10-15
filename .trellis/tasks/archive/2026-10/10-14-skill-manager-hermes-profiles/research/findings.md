# 证据与设计依据（2026-10-14）

## 当前仓库事实

| 证据 | 对本任务的影响 |
| --- | --- |
| backend/skill-manager/src/config.py，Settings.hermes_skills_root | 单一必填目标根，需要配置列表兼容层与按目标可用性 |
| src/models.py:23 TargetKey / :41 LINK_TARGET_IDS | 静态 link/export 分类需要升级；profile ID 使用独立类型 |
| src/db.py:38 deployment PRIMARY KEY(skill_id,target) | 已能存多目标部署，无需复制 registry 或多份服务状态库 |
| src/services/publisher.py，_target_root / publish / unpublish | 多处 target.value 与静态根映射；复用原子 symlink 替换和源边界 |
| src/services/install.py:41 source_state / :149 publish | 目标状态和实际执行硬编码 Hermes，需改成来源状态与组合目标状态 |
| src/api/routes.py:135 is_export / :866 _target_root / :1238 install planner | 仅改 Publisher 不够；列表、旧 API、统一预览全部必须消费 resolver |
| src/services/migration.py:104–118 | 启动重发布按固定集合和 Hermes 根，须处理动态与不可用目标 |
| src/services/operation_lock.py | 当前单 worker 内锁可复用，计划/写操作串行，不新增外部队列 |
| apps/skill-manager/src/lib/targets.ts:1 / app/page.tsx:68 | 目标类型与当前目标固定，需动态读取与 URL 保存 |
| components/InstallDialog.tsx，retry / results / items | 按 Skill ID 渲染和重试，双目标后会混合成功/失败，必须使用组合身份 |
| SourceWorkspace.tsx / SkillPool.tsx / lib/collections.ts | 筛选、徽章和合集统计直接读取 deployments.hermes，需明确传当前 target |
| docker-compose.nas.yml:398–407 | 只挂载单个 Hermes skills；新增配置不会自动赋予容器目录访问，挂载和配置需同时升级 |

## 相关任务和规范

- `.trellis/tasks/archive/2026-10/10-13-skill-manager-hermes-install/`：明确仅登记/安装分流、一次密码、多项失败恢复、旧 OpenClaw 退出。该任务的「无目标选择」是单目标旧约束，本任务引入 Hermes profile 选择。
- `.trellis/tasks/10-14-skill-manager-direct-cache-links/prd.md` 与当前 cache guide：已采用逐登记目录直接链接仓库缓存，不生成版本快照；早期 repo-pack/staging 规划不能恢复。
- 当前 frontend guide：自研单卡安装、多选仅 GitHub 成员；合集全部操作完整登记集合；下架位于安装看板。
- 当前 export guide：导出目录字段只是说明文本，export 不做 symlink 核对/启动重发布；目标分类必须保持边界。
- .trellis/config.yaml 未登记 skill-manager 包，task.py 默认误归 backend/douyin-processor；本任务 metadata 用 scope 标记 skill-manager，package 留空，不为建任务修改全局包注册。

## Hermes 上游文档

核对官方资料日期为 2026-10-14，使用 main/官方站文档，未核实用户 NAS 的实际版本：

- [Profiles 官方文档](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/profiles.md)：profile 有独立 home，skills 属于其环境状态；只有目录不代表已创建完整 profile。Skill Manager 只接受显式配置路径，不替用户创建环境。
- [Skills 官方文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)：本地、项目和外部目录存在发现优先级；源可写时既有 skills 可原位修改。推论：共享直链没有内容写入隔离，目录链接创建成功不能代替 Hermes 实际发现/读取验收。

两个已提供目录作为用户产品事实；同路径挂载可达性、具体 profile 启动方式、同名遮蔽和软链读取需实施后在实际部署验证。不读取 Hermes .env、auth.json 或整个 profile 内容以推断目录。

## 已确认产品选择

2026-10-14：用户选择配置登记，首版默认 + ohyes768，增加新 profile 时更新配置/挂载并重启；不自动发现、不自动安装到新增 profile。

## 规划审阅

已将事实归并至 PRD 背景、需求与验收；design/implement 分别记录技术契约与步骤。当前无待回答的产品选择，等待用户审阅完整规划。未修改业务源码、未运行实施测试或操作实际 Hermes 目录。

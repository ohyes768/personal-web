# 规划依据（2026-10-13）

## 用户决策

本会话已明确：按仓库整包管理，不选子 skill；Hermes/OpenClaw 软链直接指向仓库，git 更新不换链接；本次仅建 Trellis 任务规划。此前版本快照建议已被用户替换，不能再次引入。

## 本地代码与历史

| 位置 | 已核实事实 | 设计影响 |
| --- | --- | --- |
| backend/skill-manager/src/services/git_cache.py:457 | repos/<owner>__<repo> 缓存共用；fetch --force + checkout --force revision | 复用路径/进度执行器，另建分支更新 |
| 同文件 :397 / :700 | scan 复用缓存或临时 clone，递归候选与引用粗匹配 | 准备持久包仓库并生成只读库存 |
| backend/skill-manager/src/models.py:85 | RegistrySkill 单条以 repository + path 定义 | 新增包模型，不假装 root 有 SKILL.md |
| backend/skill-manager/src/services/publisher.py:79 / :150 / :332 / :382 | root 校验、staging、原子链接、两目标根映射 | 包验证与链接逻辑分离，两目标共用包服务 |
| backend/skill-manager/src/services/migration.py:86 | 启动重新 staging 并发布 active skill | 已归并/转换的旧记录须排除 |
| backend/skill-manager/src/services/task_manager.py:46 | 内存线程、202 轮询、30 分钟保留 | 扩充 pack prepare/update/convert，复用任务平台 |
| apps/skill-manager/src/components/RegisterGithubDialog.tsx:20 | 候选/共享资源多选、单批分流 | 替换为包预览/添加 |
| apps/skill-manager/src/components/SourceWorkspace.tsx:74 | skill_id 队列与发布计划 | GitHub 包操作与自研兼容 |
| .trellis/spec/guides/skill-manager-export-targets.md | ZIP 仅登记子目录，哈希和台账独立 | 不把全仓 ZIP 冒充旧格式 |
| .trellis/tasks/archive/2026-09/09-21-skill-host-path-symlinks/prd.md | 宿主 Agent/容器路径曾造成断链 | 同路径挂载继续验收 |

历史：b0ee0fe（2026-09-20 单技能扫描）、ebe43f9/fa7f4c5（2026-09-30 ai-berkshire 批量登记、共享缓存、tools 依赖修复）、f67f15f（2026-10-02 候选描述）。这是替换 GitHub 管理单位，不只是调整候选列表。

## 上游能力（已浏览，不代表 NAS 安装版本）

- Hermes 官方：https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
  - 默认 profile root ~/.hermes/skills，支持 skills.external_dirs；技能索引按需加载。
- Hermes 源码：https://github.com/NousResearch/hermes-agent/blob/main/agent/skill_utils.py
  - iter_skill_index_files 使用 os.walk(..., followlinks=True)，递归跟随目录软链；支持目录/排除项会被剪枝。
  - 包目录名不自动给技能 frontmatter name 增加命名空间，同名冲突须检测。
- OpenClaw 官方：https://docs.openclaw.ai/tools/skills
  - 配置根下支持最多六层分组目录；遇到 SKILL.md 会停止该目录以下遍历。
  - workspace/project/extraDirs 的软链真实目标须在根内，或配置 skills.load.allowSymlinkTargets。
- OpenClaw 配置：https://docs.openclaw.ai/tools/skills-config
  - 只增加受控仓库路径的信任；核实 watch/重载行为。
- ai-berkshire 示例：https://github.com/xbtlin/ai-berkshire/blob/main/codex-skills/investment-team/SKILL.md
  - Codex adapter 要求定位 checkout root、tools/、AGENTS.md；文件布局完整不表示 Agent API 功能自动等价。

## 数量与验证门槛

2026-10-13 gh api 主分支递归文件树计数：ai-berkshire 为 22，taste-skill 为 13 个 SKILL.md；README“20个”不是计数依据。生产始终按当前仓库扫描。

实施时必须核实 NAS 两 Agent 的版本/profile/生效路径、整仓根软链递归清单、OpenClaw 信任配置、工具运行环境及更新后的刷新。若任一目标不支持，记录具体不兼容，不能用逐技能链接冒充“一包一条链”。

## 实机证据与方案修正

- NAS Hermes 当前 CLI v0.18.2，gateway 使用 pre-upgrade-backup 目录的运行时；
  两处 loader 均 os.walk(followlinks=True)。
- NAS OpenClaw 2026.4.11 的包装层仅扫描技能目录一层，依赖库的递归支持
  不代表包装层递归。隔离临时根软链探测：rootSymlink=0，
  groupThroughSymlink/codex-skills=22；Hermes 同一根软链发现22项。
- 保留一包一条根链，由适配器自动维护通过该链访问的分组 extraDirs；
  用户仍无子技能选择。OpenClaw 实际配置是标准 JSON，适配器仅定向修改列表。
- 新代码未部署 NAS。向 NAS 上传私有验证包被自动审批拒绝，未绕过；
  原拟本机 WSL 验证随后由用户明确取消，最终只运行 Windows 必要测试。

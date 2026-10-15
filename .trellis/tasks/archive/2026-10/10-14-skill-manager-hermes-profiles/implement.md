# 实施计划

状态：in_progress，用户已批准实施；功能和验证已完成，等待提交确认。当前 Codex 默认 inline，单任务覆盖同一条目标配置→计划→安装→展示链路，无需父子任务或分派代理。

## 1. 上下文与基线

- [x] 加载 trellis-before-dev，读本任务 PRD/design/research 和四份 skill-manager guide；guides 中旧固定 link 集合、单目标统计与早期 staging 说明按本任务要求升级，不能盲目沿用。
- [x] 重新检查工作区与最新提交，保留其他任务改动；确认现有直链、统一安装、合集完整下载已落地，依据当前代码实现。上线前只核对现有 HERMES_SKILLS_ROOT 的绝对路径与实际环境归属，不为默认显示名称变更旧目标根。
- [x] 全局搜索 `hermes_skills_root / TargetKey.HERMES / LINK_TARGET_IDS / deployments.hermes / agent='hermes'`，形成所有目标解析和分类消费者清单，包括旧 API、启动迁移、源清理及隐留队列工具。

## 2. 目标模型、配置与目录解析（R1/R5/R6）

- [x] models.py 定义独立 InstallTargetId、目标配置/响应模型，保留默认 `hermes` 与现有 export ID 约束。
- [x] Settings 读取 SKILL_MANAGER_HERMES_TARGETS，未设置时兼容原 HERMES_SKILLS_ROOT；校验结构、唯一 ID、绝对路径、根重复/互相包含。目标缺目录降级为不可用。
- [x] db.py 添加幂等 install_target catalog，区分持久身份与当前配置授权；保留 legacy deployment/history，禁止有 active 台账时同 ID 迁往另一根。
- [x] 新增 TargetResolver 并初始化到 app.state；通过依赖注入提供目标清单、分类、当前根/目录身份验证与不可用原因。
- [x] 所有发布、下架、列表核对、导出边界和启动迁移统一用 resolver，去掉「非固定 Hermes 即 export」推断；未配置目标绝不从数据库路径恢复写权限。
- [x] 未配置目标的 active 台账继续参与 registry/cache 删除保护；默认 ID、退役 OpenClaw 迁移和导出历史兼容验证。

## 3. 多目标计划与执行（R3/R4）

- [x] 新增 GET /api/skills/install-targets（放在冲突的动态路由前），响应名称/profile/实际目录/配置状态/可用性。
- [x] Preview 支持 items 精确组合、候选 + target_ids，以及原请求默认 hermes 的兼容模式；互斥输入、未知/空目标和容量错误在来源准备前拒绝。
- [x] Plan 来源状态按 Skill/仓库复用，目标状态按组合保存；目标配置指纹、目录身份、目标链接与影响集合变化使计划失效。
- [x] InstallManager 来源准备/登记各一次，随后逐目标发布；结果附 target。保留锁、request_id、计划 TTL、任务回收与密码隔离。
- [x] 预览补 affected_installations；缓存更新一次、其他直链 profile 实际版本统一刷新；不可用 active profile 也列可能受影响。
- [x] legacy publish/plan/unpublish、Clone 影响说明和启动重发布全部跟进，不能留下静态枚举回退。

## 4. 前端 profile 流程（R2/R3/R4）

- [x] lib/targets.ts、types.ts、api.ts 动态安装目标类型/清单请求，与 ZIP export 类型分开；target 路径参数统一编码。
- [x] page.tsx 读取目标清单，URL target 保存当前目标；兼容旧 URL、加载错误、未知目标和不可用目标，异步加载不得静默选错环境。
- [x] SourceWorkspace/SkillPool/collections 使用当前 target 计算徽章、筛选、计数和操作；自研正常直链仍无需更新按钮。
- [x] InstallDialog 展示目标多选和目录，默认只选当前 target；选择变化重新预览，忽略过期响应。渲染、进度和结果按组合键计数。
- [x] 失败重试转换为 items 中的失败组合，已登记候选不重新登记；影响提示包含未选择但共享缓存的 profile。
- [x] DeployBoard 下架只操作当前 target，合集全部语义不受筛选裁剪；仅登记、导出、合集下载和来源导航保持可用。

## 5. 配置与文档（R1/R6）

- [x] docker-compose.nas.yml 注入 JSON 目标配置并提供独立 profile skills 同路径挂载；旧 env 仍能单目标启动，第三目标通过 override 添加示例。
- [x] scripts/start-skill-manager-dev.bat 提供两目标模拟目录/配置，尊重用户覆盖；不挂真实 profile 凭据。
- [x] docs/skill-manager-nas-setup.md 写实际绝对路径、新增目标步骤、只读目标配置说明、共享源更新影响、目标不可用/移出配置处理和数据库回退限制。
- [x] 更新 skill-manager frontend/export/cache guides 和 guides/index 的过时摘要，记录 resolver 分类与 source/target 计划边界。

## 6. 实施阶段验证

覆盖行为场景而非复制实现：

- 配置缺省兼容/两目标/三目标；重复或重叠根、非绝对路径、缺目录、同 ID 换根、有安装目标移出配置。
- 旧库重复升级，legacy hermes 台账和链接不变；profile 记录不进入 export 分支，退役 OpenClaw 不复活。
- 同 Skill 双目标成功、A 成功/B 普通目录冲突、只重试 B、登记一次、prepare 一次；未知目标和错误密码无副作用。
- 计划后改目标根/替换目录/改链接/改源/改影响集合、重复 request_id、任务重启丢失。
- 同仓库两个 profile 多成员共享更新、未选择 profile 也列影响、单目标卸载其他链不变；未配置 active 目标阻止源清理。
- UI profile 切换与 URL 恢复、徽章/合集完整计数、加载失败、单/多目标弹窗、过期响应抑制和精确失败重试；仅登记与 ZIP/完整合集下载回归。

按各目录执行：

```text
backend/skill-manager:
  uv run pytest tests/test_config.py tests/test_db.py tests/test_publisher.py tests/test_direct_cache_links.py tests/test_hermes_migration.py tests/test_api.py tests/test_targets.py
  uv run pytest

apps/skill-manager:
  pnpm test
  pnpm exec tsc --noEmit
  pnpm lint
  pnpm build
```

新增多目标专项测试文件后纳入针对性命令。Windows symlink 特权或 standalone 输出限制若实际发生，明确记录跳过/失败及其边界；不以 mock 当作真实链接验收。浏览器模拟 API 覆盖 profile 交互，应用自检和实际 Hermes 验收分开记录。

真实 NAS/Hermes 验收作为后续部署清单：记录已安装版本和实际 profile home，在两环境各发现/读取同一技能，确认来源路径在 Hermes 执行环境可达；确认是否有本地同名技能遮蔽。真实环境操作需要用户后续部署指令，本轮规划不执行。

## 7. 风险文件、交付与回退

风险集中在 `config.py/models.py/db.py` 的分类/旧库初始化、`install.py` 的指纹和失败重试、`routes.py/migration.py` 的所有旧目标解析、`page.tsx/InstallDialog.tsx` 的晚到响应。

- [x] schema 仅追加；旧库首次升级自动备份并有回归测试。实施只使用测试 SQLite，未修改真实运行库。
- [x] 后端兼容旧客户端，部署说明记录先后顺序；新增 profile 不自动安装。真实部署另行执行。
- [x] 技术检查通过后记录 verification.md，审阅对照 PRD AC1–AC8；没有实际 Hermes 验证时保留部署验收项。
- [x] 回退后端需使用备份旧库，不能用旧固定分类代码直接读取新 profile 行；已创建链接仍需源路径可达。
- [ ] 等待用户一次性提交确认；真实 NAS 部署与 Hermes 发现验收留待后续部署指令。

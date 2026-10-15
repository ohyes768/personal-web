# 技术设计：仓库包直链

## 1. 已确定的边界

- GitHub 的管理与安装单位是 repository pack；自研仍是 RegistrySkill。
- 每目标一条软链指向稳定 checkout 根，两个目标共享内容；不会按目标保留不同版本。
- 用户手动“更新仓库”直接改变已安装内容。Git commit 是内部可观测状态，不是路径版本。
- 此文件是拟实施设计，当前尚未改业务代码/运行 NAS 操作。

## 2. 文件布局与发现

沿用 GITHUB_SKILL_CACHE_ROOT/repos/<owner>__<repo>/，避免再次 clone：

    cache/repos/xbtlin__ai-berkshire/
      .git/
      codex-skills/<skill>/SKILL.md
      tools/
      skills/
      AGENTS.md

    HERMES_SKILLS_ROOT/github-xbtlin-ai-berkshire -> cache/repos/xbtlin__ai-berkshire/
    OPENCLAW_SKILLS_ROOT/github-xbtlin-ai-berkshire -> 同一目录

根有 SKILL.md 的单技能仓库同样按包安装。根有 SKILL.md 且还包含独立子技能的混合布局，须检查两 Agent 停止遍历规则；不得宣称所有子项都可发现。

不创建 wrapper SKILL.md，不拼装 tools，不把 .git 拷贝出去。软链包含整个仓库，Agent 扫描应跳过 .git/缓存/支持目录；库存扫描与目标实际发现清单必须对照。六层深度与剪枝造成不可发现的技能作为兼容诊断。

包 ID 使用稳定 github-<owner>-<repo> 规范，沿用合法 ID 长度约束，截断后附确定性摘要解决超长与冲突；repository 的规范化唯一键为真源，不能仅靠包名去重。目标有同名普通目录则 blocked，不派生新名字悄悄重复安装。

## 3. 数据模型（拟新增，不让根目录冒充 RegistrySkill）

新增：

- github_pack：id、repository（规范化唯一）、name、summary、tags、tracking_branch、current_revision、last_checked_revision、checked_at、updated_at、inventory_revision、state。
- github_pack_inventory：pack_id、path、name、description、valid/diagnostic。每次准备/更新按该 HEAD 替换库存，是发现缓存，不是独立登记。
- github_pack_deployment：pack_id + link target 唯一、status、link_path、last_verified_revision、verified_at、compatibility/error、legacy_conversion_state。
- github_pack_history：包动作、目标、before/after revision、时间、结果、错误；不写密码。
- legacy_github_pack_member：旧 skill_id -> pack_id，对账、历史/导出兼容和防止旧写入口误用。

不要把 current_revision 与 deployed_revision 解释成两份内容。所有直链目标读取 checkout HEAD；旧安装/上次验证 commit 独立记录。缓存丢失显示 source_missing，不虚报可用。

SQLite 迁移加表/唯一索引/一次性标记，保留旧 registry_skill、deployment 和导出台账，不先删除旧数据。包标签初始化为旧标签并集，名称采用仓库名，旧技能简介和标签仍可在历史/成员信息中追溯。

## 4. 操作与 API

拟新增 /api/github-packs 系列，models.py 为 Pydantic 唯一契约源：

| API | 行为 |
| --- | --- |
| GET /github-packs | 包卡片与目标状态；只读、不 checkout |
| POST /github-packs/prepare | URL + password，202 prepare_pack；复用或下载整仓并返回库存预览 |
| POST /github-packs | 由服务器校验准备结果，登记整包；不可接受任意路径 |
| GET /github-packs/{id} | 只读内部清单、兼容诊断与历史 |
| POST /github-packs/{id}/check-update | 远端元信息检查，工作树不变 |
| POST /github-packs/{id}/update | password，202 update_pack；同仓库锁 |
| POST /github-packs/{id}/plan | targets，预览安装/旧安装转换及冲突 |
| POST /github-packs/{id}/install | password + targets，202 install_pack；按目标返回结果 |
| DELETE /github-packs/{id}/targets/{target} | password，卸载包链接；不删除仓库 |
| DELETE /github-packs/{id} | password，引用校验后移除登记/无引用仓库 |

路径完整挂 /api 前缀；固定 target 仅 hermes/openclaw，动态 export 不进入 link 接口。复用现有 tasks 查询与 TaskProgressDialog；TaskKind/stage/type 两端同步扩展，保持 202 前等待、运行进度、404 task_not_found 和可重试错误契约。

旧 GitHub scan/单/批登记接口逐步停止前端调用。对已映射包的旧 clone/publish/check-update 写行为返回 pack_managed 和包 ID；不得用旧 ensure_cached 按子技能 revision 检出仓库。未转换的 legacy 仓库也限制工作树修改，防止混用破坏迁移判断。

错误至少区分 no_skills、repo_busy、dirty_worktree、branch_diverged、branch_changed、cache_missing、target_conflict、target_incompatible、update_failed、conversion_failed；沿用 unreachable/download_timeout 等网络错误。

## 5. Git 同步与互斥

- 复用 normalize_repository、repo_cache_dir、固定 argv Git 执行器、流式 clone 进度和首次 .tmp 原子落地；新包验证 Git repository + 至少一项有效 inventory，不要求 root SKILL.md。
- 首次 clone 跟踪远端默认分支，保存 tracking_branch；已存在旧 detached checkout 先判 clean，再解析默认分支。只在已验证祖先关系与无分叉时建立/切回跟踪分支，不强制重写已有分支。
- 更新等效 git pull --ff-only：检查 clean、读取默认分支、fetch 指定分支、验证候选树的技能、验证可快进，再 merge --ff-only。不要旧 fetch --force + checkout --force；默认分支变化报告明确诊断，不自动改分支。
- fetch 失败不改变 checkout。目标提交零技能等可提前验证的错误在落地前阻止；落地后重新扫描并读取 HEAD，事务更新库存和审计。
- 更新时路径和软链 inode 不变；不 rename/替换仓库目录，不让链接指向 .tmp；就地 Git 更新不具备多文件读取原子性。
- 文件系统异常/进程中断后读取实际 HEAD、工作树和库存，显示 needs_repair 或可重试，不能用一次 DB 写入假装更新原子完成，也不自动 reset/clean 用户修改。
- 锁以规范化 repository 为单位覆盖 prepare/更新/安装转换/删除；单进程当前部署可用仓库锁，若多 worker 必须补跨进程锁后才上线。两目标安装复用同一内容，不各自 fetch。
- 发现本地 tracked 或可能冲突的 untracked 改动明确报告，用户处理后重试；不把 Agent 修改悄悄清掉。

## 6. Publisher 与目标适配

引入 PackService/PackPublisher，组合原 Publisher 的受控路径、临时链接、os.replace 原语，避免复制两套安装逻辑；单技能 validated_source 不能直接复用包校验。

包校验：目标 checkout 在受控 repos 根、对应已登记 repository、Git HEAD 可读、库存有效。软链创建仅限配置的目标根；跟随仓库内部逃逸链接的资源不认作可用库存。

Hermes：核实实际 profile root 和安装版本递归 followlinks；验证列表/skill_view/内容刷新。直接包软链无需再切换为 external_dirs 方案。

OpenClaw：核实 workspace vs managed root；workspace 外部软链需要 allowSymlinkTargets 时，在部署配置中仅增加受控仓库目录。配置变更需保留已有设置、原子写入/备份与可复查差异，不通过写宽泛 HOME 解决。规划默认用现有目标根，不擅自换到其他 workspace。

状态区分“链接已创建”和“Agent 已识别”；尚未运行 Agent 验证不能标已验证。旧版本不能识别整包时停在兼容阻塞，不生成逐技能链接或 wrapper 绕过用户要求。

完整 ai-berkshire 根布局保留 tools/，Agent 读到原始 SKILL.md 后需定位该 checkout 根执行命令。验证宿主路径也能在其 terminal/sandbox 访问；若只能看到隔离路径，调整受控挂载或报兼容问题，不能承诺复制文件已解决执行。

## 7. 存量迁移与失败恢复

1. 启动建立 repo -> pack -> legacy skill 映射，保留原文件/历史；不联网、不自动整包安装。
2. 有旧 active skill 的目标展示 legacy_pending（曾经部分安装不算包已安装）；列出将替换的旧链接和已准备仓库 HEAD，可在详情查看旧 commit 差异。
3. 用户按目标执行一次包转换。先验证 clean 仓库、Agent 兼容/配置和可替换的旧链接；对未知/被用户改指的链接停止，不能按名称盲删。
4. 准备包临时链接并保存旧链接目标/数据库状态作为迁移恢复记录；在受锁的短窗口替换为正式包链接并移除确认归属的旧链接。多链接不能声称跨文件原子；成功后 Agent 清单刷新验收。
5. 任一步失败按记录恢复旧链接/状态，或保留 conversion_failed 恢复任务；重启识别未完成迁移，不能同时长期保留新包和旧子链造成重复发现。
6. 转换后的 legacy 记录从旧自动重发布路径排除。仅无引用的旧 staging 才可清理；旧不同 revision 安装在转换时明确统一到当前 checkout，不隐瞒行为变化。
7. 删除包先确认两个目标、所有 legacy 和导出兼容引用；active 引用阻止删除。无引用才清理受控 repository，其他包不受影响。

数据备份与旧链迁移恢复只用于上线故障恢复，不引入用户版本选择/发布回滚功能。

## 8. 前端与导出边界

保留管理/部署/导出目标 URL、local/github tabs 和 Next basePath 规则。GitHub 区改为包卡片，添加弹窗只有 URL/进度/包预览/登记，库存只读。

包操作：添加、安装目标、检查更新、更新仓库、卸载、删除；“更新”不进入旧发布队列。目标未安装可安装，已直链只显示已安装/链接异常/识别诊断；不显示待发布新版。

自研仍走原 SourceWorkspace/队列。可抽取卡片/筛选/确认组件，但不要用 SkillCard 强制塞包字段导致两端隐式类型漂移。

动态导出目标、自研/旧单技能 ZIP API 与台账保留，GitHub 包卡片不提供假整包导出；历史导出记录可在包详情关联查看。未来包导出需要另定目录/内容契约。

## 9. 风险与上线门槛

这是用户明确选择的共享可变工作树模型；网络 fetch 可与旧读取并存，但落地时可能与运行中 Agent 读取交错。界面说明即可，不引入被否决的快照。

上线须实际版本支持“包根软链 + 嵌套扫描”、定向信任配置、工具运行路径和无引用误清理；Windows marker 跳过不算完成 Linux 软链验收。研究依据见 research/findings.md。

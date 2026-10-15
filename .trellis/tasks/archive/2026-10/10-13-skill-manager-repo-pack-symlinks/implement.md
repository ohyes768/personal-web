# 执行计划

状态：in_progress。用户已要求实施，最新明确仅做 Windows 测试，停止 WSL。
核心实现与针对性审查修复已完成；最终验证结果见 verification.md。

## 1. 实施前门槛

- [x] 用户要求实施后按 Trellis 激活任务，读取 trellis-before-dev 和相关 spec；检查工作区已有变更，不覆盖其他任务。
- [ ] 核实 NAS Hermes/OpenClaw 版本、真实生效根、运行 UID、工具 sandbox、OpenClaw trust 配置及服务刷新命令，记录 research 中。
- [ ] 用隔离测试仓库验证一条根软链的多层扫描与 tools 可达；不支持时记录具体阻塞，不改为逐 skill 链接。
- [ ] 确认 API 只运行单 worker，否则在仓库级互斥中实现跨进程锁。

## 2. 数据与契约

- [ ] models.py 定义 pack/inventory/deployment/history、请求/响应、诊断码，保持 target link/export 边界。
- [ ] db.py 增加表、唯一键、legacy 映射、幂等迁移，包标签归并保留原成员元数据。
- [ ] 先写旧多登记/不同目标/版本/导出台账保留的迁移测试；旧数据不删除。

## 3. 仓库准备与更新

- [ ] 新 PackService 或仓库级方法复用 git_cache 的 URL/缓存路径/固定 argv/流式进度。
- [ ] 支持 root 没有 SKILL.md 的完整 repository 库存；根/子层剪枝和目标差异有诊断。
- [ ] 仓库锁、clean/快进验证、默认分支、旧 detached 转换；零技能候选提前拒绝。
- [ ] 手动更新等效 pull --ff-only，路径不变，无 staging/强制 checkout；更新后 HEAD/库存/审计同源。
- [ ] 覆盖 dirty/diverged、分支改变、网络/超时、落地异常、重启恢复与并发；旧接口防止改写包 checkout。

## 4. 包软链与存量转换

- [ ] PackPublisher 组合原受控路径与原子链接原语，验证包源而非顶层 SKILL.md。
- [ ] 每包每目标一条根链接；安装独立目标，不更新 Git；已装无需再次发布。
- [ ] 目标计划/兼容检查/冲突处理；OpenClaw 定向 trust 配置与 Hermes profile 验证。
- [ ] legacy_pending 一次转换，先预检，再按记录替换/撤链；失败恢复与重启幂等。
- [ ] 原 migration.py 启动重发布跳过已归并/转换记录；清理旧 staging 前检查引用。
- [ ] 卸载单目标不删仓库；包删除检查 active/legacy/兼容引用，不覆盖普通目录。

## 5. API、任务与前端

- [ ] routes.py 新 /github-packs API；task_manager 新 prepare/update/install/convert，密码仅同步鉴权，不入任务。
- [ ] API 包列表、库存、检查/更新、计划/安装、卸载/删除与部分目标失败响应测试。
- [ ] 前端 types/api/useGithubTask/format 与服务端契约同步；保留 202 前等待与失败可重试。
- [ ] RegisterGithubDialog 改包入口，无候选/共享资源选择；新增包卡片/库存详情与目标状态。
- [ ] GitHub 包更新不再进入旧发布队列；local 流程、导航、标签与导出目标回归。
- [ ] 旧安装转换结果、影响所有已装目标的更新提示、缓存丢失/不兼容状态可读。
- [ ] 包无未实现 ZIP 导出按钮；旧导出 API/历史保留与包详情关联。

## 6. 验证

从各项目目录运行，basetemp 在项目盘；记录实际结果，不能提前标通过。

后端 backend/skill-manager：

    uv run pytest tests/test_models.py tests/test_db.py tests/test_git_cache.py tests/test_publisher.py tests/test_task_manager.py tests/test_api.py tests/test_exporting.py tests/test_local_sync.py
    uv run pytest tests/

新增 meaningful tests 建议为 test_github_packs.py、test_pack_migration.py，纳入全量；实链测试使用 requires_symlink，不能用普通目录冒充。

前端 apps/skill-manager：

    pnpm lint
    pnpm exec tsc --noEmit
    pnpm test
    pnpm build

按用户最新要求只做 Windows 验证。standalone build/symlink 受限时记录真实结果；
NAS 已有 Agent loader 的隔离探测作为目录发现依据，不宣称新业务代码已在 Linux 全量测试。

- [ ] Linux 真实 fixture 上游包含嵌套技能/tools，两个 target 各一条链；修改/新增/删除上游文件，更新后 readlink 与链接 inode 不变，两目标内容变化。
- [ ] 不创建 staging/rev，无 root SKILL.md 仍可安装；脏工作树不覆盖；检查更新不改 HEAD。
- [ ] 存量部分安装/多版本转换及故障注入，失败恢复后无重复技能，重启不恢复旧 staging。
- [ ] 在真实 NAS 分别用两 Agent 的清单/读取命令验证，ai-berkshire 工具一次真实调用、taste-skill 全文读取；记录期望/实际名称集合。
- [ ] 管理台浏览器验收：添加整包、安装两目标、更新一次、单目标卸载、重复添加、错误重试；截图确认无子技能勾选。

## 7. 文档与上线

- [ ] 更新 .trellis/spec/guides/skill-manager-github-cache.md、frontend.md、registry-sync.md、export-targets.md，明确本任务替代的 staging/子登记契约。
- [ ] 更新 docs/skill-manager-nas-setup.md 和 deploy/README-same-path-mounts.md：稳定仓库路径、包根软链、受控 trust、两目标一起更新、dirty 处理。
- [ ] 对 /api/github-packs、任务查询核实 Next rewrite 与 Nginx 路由实际覆盖，必要时补配置。
- [ ] 上线前备份 DB/链接清单和旧快照引用；启动只迁数据，包转换经明确操作，迁移失败按恢复记录处理。
- [ ] 不自动清理尚有引用的快照/仓库；所有 AC 有证据后再进入 finish-work。

## 主要改动范围

- backend/skill-manager/src/{models,db,main,config}.py、api/routes.py、services/{git_cache,publisher,registry,migration,task_manager}.py，新增包服务。
- backend/skill-manager/tests/；apps/skill-manager/src/components/、src/lib/ 与页面数据加载。
- 相关 Trellis spec、NAS/同路径挂载说明及必要代理配置。

## 故障恢复边界

迁移失败恢复旧链接/台账；升级撤回业务版本前验证新旧 DB 的兼容映射。就地 Git 更新失败诊断实际 HEAD 和 dirty 状态，不自动 reset，也不把旧快照回滚作为新包功能。

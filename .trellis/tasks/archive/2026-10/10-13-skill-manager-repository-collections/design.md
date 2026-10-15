# 设计

## 方案选择
推荐派生合集：使用现有 SkillCard.repository 归组，不创建合集表。相比持久化合集实体，省掉迁移与成员同步；相比只增加折叠标题，还提供完整的批量操作与状态摘要。

## 数据与界面
新增纯函数合集模块，规范化 URL 并使用完整 owner/repo 作为稳定 key。优先使用后端已规范化地址；无有效仓库地址的历史条目保留独立可见项并提示异常，不丢弃。
聚合前保留完整成员集合，筛选结果仅控制可见成员；合集总数与动作使用完整集合。统一定义 ready/active/link_missing/blocked 等成员判定，管理与部署看板复用。
SkillPool 中 GitHub 使用合集卡片，自研沿用单项。SourceWorkspace 承接合集入队，复用 addQueueTarget；不通过连续 toggle 实现“全部加入”，避免把已入队项移出。
RegisterGithubDialog 在新扫描完成时初始化全选，默认展示总数和折叠详情。现有 batch API、共享资源选项、扫描等待与失败恢复保持。
DeployBoard 合集内展示成员；批量下架处理选中 Agent，维护待执行列表与逐项结果，成功项从重试集合移除。

## 更新与错误
检查更新继续只读；缓存缺失时从同仓库代表成员触发一次 Clone 后刷新完整列表，不伪造全部成功状态。发布按原 recorded revision 与 staging 契约执行。
如果现有接口不能对同仓库统一完成必要动作，再添加最小批量服务；须明确成员 revision 同步和部分失败，不让 UI 假设一次 Git fetch 就等于所有登记/部署已更新。
保持原有 shared_paths、缓存引用保护和导出规则。合集管理不删除仓库目录，不引入清理脚本。

## 相关文件
apps/skill-manager/src/components/{SkillPool,SourceWorkspace,RegisterGithubDialog,DeployBoard}.tsx
apps/skill-manager/src/app/page.tsx
apps/skill-manager/src/lib/{queue,format,types,api}.ts
.trellis/spec/guides/skill-manager-{frontend,github-cache,registry-sync,export-targets}.md

## 兼容与撤回
无需数据库迁移；发布软链和快照不变化。撤回本次 UI 改动即可恢复单项展示。保留当前工作区其他任务及尚未提交的清理脚本移除改动。

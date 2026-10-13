# 实施计划

1. 阅读 skill-manager frontend/github-cache/registry-sync/export-targets 规范，核对现有更新、发布、下架结果契约。
2. 实现并测试仓库 key、成员分组、状态聚合与搜索匹配纯函数。覆盖 URL 差异、不同 owner、混合状态、缺失地址。
3. 管理看板新增合集卡片、折叠成员、数量摘要与全部加入队列；覆盖去重、筛选后操作完整集合与自研不变。
4. 添加对话框改默认全选与详情折叠；测试新扫描清空旧选择、错误恢复、单成员/多成员和共享资源预选。
5. 整合仓库级检查更新与缓存恢复，先复用现有 API；必要后端扩展另补针对性测试。
6. 部署看板归组与批量下架；测试部分失败、剩余项重试、Agent 隔离以及原单项操作。
7. Windows 验证：apps/skill-manager 下 pnpm vitest run、pnpm tsc --noEmit、pnpm next lint；如改后端，运行其 .venv/Scripts/python.exe -m pytest 相关测试。浏览器核对 ai-berkshire 合集交互（使用本地数据/模拟接口，不写生产）。
8. 更新相关前端契约，记录检查结果与 Windows symlink 限制。不得用跳过 symlink 测试声称 NAS 部署验证成功。用户未要求提交、推送或部署时不执行。

规划完成，暂不运行 task.py start，不修改业务代码。实施时按以上顺序单代理执行，避免不必要的并行与重复研究。

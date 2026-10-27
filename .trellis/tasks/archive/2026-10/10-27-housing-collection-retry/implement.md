# 实施计划
- [x] 先写失败项筛选、只请求失败详情（含同 ID 不同 kind、忽略、取消、错误恢复）、API 模式和按钮状态测试，运行确认失败。
- [x] directory_collection.py 增加失败目标投影、重试模式与持久化状态计数，保留原全量默认。
- [x] directory_routes.py 加 Literal 模式并转交任务；DirectoryFlowWorkspace.tsx 加按钮与文案。
- [x] 跑后端相关 pytest（项目盘独立 basetemp）、前端 node 测试、lint、tsc 和 build；修复问题。
- [x] 更新目录流程 spec 与任务验证记录；交付本地改动，不操作线上采集数据。

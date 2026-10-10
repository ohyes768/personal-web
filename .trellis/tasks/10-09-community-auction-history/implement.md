# 执行计划（尚未开始）

1. 用户审阅并要求实施后task.py start，加载trellis-before-dev、法拍/准入/跨层/Windows测试规范。
2. 核验社区名录、真实成交样本和asset_id跨轮次稳定性，记录证据。
3. 写关键统计与匹配测试，实现查询时关联、显式映射、去重、边界筛选、全结果统计及分页。
4. 接入批量汇总及小区历史路由，验证404/422/503和既有API兼容。
5. 定义前端契约，提取小区详情，实现页签、筛选、统计卡、列表与风险/轮次展开。
6. 地图信息入口接数量，检查无N+1请求、筛选及切换竞态。
7. 真实样本端到端验收、移动端与键盘检查，更新API文档及Trellis契约。

## 验证
后端：在backend/housing-map执行 .venv/Scripts/python.exe -m pytest --basetemp=.pytest-tmp-auction -q。
前端：实施前核验仓库包管理器与锁文件，运行housing-map的lint、TypeScript检查、build。
检查git diff --check；按prd AC1–AC6逐项验收。浏览器检查加载/空/失败、分页筛选与快速切换，使用应用预览，不访问此前被阻止的拍卖入口。

## 主要文件与风险
后端新增历史查询/匹配服务及映射配置，扩展auction_routes.py和测试；前端page.tsx、globals.css、lib/types.ts及独立详情组件。地图接入前核验BinjiangMap接口，避免大量永久标签遮挡。
重点防止重名误配、重复轮次、无时区日期和稀疏数据误导。仓库含其他任务改动，不回退或提交它们。回滚仅撤销新增展示与路由，保留数据。

## 状态
仅规划，未改应用代码、未开始实现、未提交或部署。

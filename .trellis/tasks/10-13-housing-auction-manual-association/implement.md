# 执行计划（实现与验收完成，待提交）

1. 审阅prd/design，明确与正在进行的住宅目录/租金任务边界；读取housing-map backend/frontend指南与相关最新代码，冻结同步API及界面定位参数。
2. 实现共享法拍记录到目录同步，保留房产/轮次身份、忽略和人工决策；补同步使用累计存储，无上游调用。
3. 在成功采集发布后接入同步与结果报告；处理跨存储失败和只重试同步。
4. 接通法拍未关联列表到现有手工绑定能力，展示缺失原因、候选与搜索；绑定后刷新法拍和小区统计。
5. 针对身份去重、旧历史补入、自动证据、人工优先、并发删除及同步失败编写有意义的后端测试。
6. 验证前端错误/空状态、重复操作、390px布局与绑定后即时归属；隔离数据库，不动线上目录。
7. backend/housing-map运行 .venv/bin/python -m pytest tests -q --basetemp=/tmp/housing-auction-association-tests；apps/housing-map运行 node --test tests/*.test.cjs、npm run lint、npx tsc --noEmit、npm run build。
8. 全范围审查，记录验收与必要spec变更；按工作流展示提交计划，未经授权不提交/部署。

## 关键文件
auction_refresh.py、auction_store.py、auction_history.py、community_registry.py、directory_routes.py、AuctionDataList.tsx、CommunityManagement.tsx及父页面刷新协调。当前工作区其他任务修改不覆盖、不打包提交。

## 开始门槛
用户已授权并执行task.py start；实现和验收结果见verification.md，待提交确认。

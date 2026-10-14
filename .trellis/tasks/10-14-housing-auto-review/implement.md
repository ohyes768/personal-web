# 自动审核与住宅自动收录

## 执行顺序
- [x] 任务1/2验收通过、用户明确开始后激活本子任务；检查人工锁与候选事务接口。
- [x] 写判定矩阵测试，先覆盖江汉路/只有高德/法拍标题/同名异址/分期/最新失败/混合类型/人工锁。
- [x] 实现纯判定引擎与只读固定快照预演，生成可解释报告，不改业务状态。
- [x] 检查隔离旧数据预演结果，统计误收录/疑点/人工锁，记录规则与审阅结论。
- [x] 实现幂等执行、启用开关、执行前revision/锁重检查、报告与自动标记；不自动启用生产。
- [x] 验证采集后候选更新再审核、新轮次、人工撤销与恢复保锁，完整三个子任务集成回归。
- [x] 写verification.md/规则文档，交总任务汇总验收；正式数据迁移/启用另行授权。

## 验证重点
新增test_community_auto_review.py/test_community_auto_review_integration.py，复用前两任务状态/候选测试和directory_collection/residential_classifier/auction_association；隔离预演前后业务表校验与浏览器撤销回归。

## 验证命令与环境
后端cwd=backend/housing-map，Windows使用本项目.venv与项目盘独立basetemp：

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp-housing-auto-review
```

先执行本子任务定向测试，再完整回归。前端cwd=apps/housing-map：

```powershell
npm run lint
npx tsc --noEmit
node --test tests/*.test.cjs
npm run build
```

用HOUSING_DATA_DIR隔离副本与桌面/手机浏览器验证。Windows/WSL不共享临时目录。记录verification.md，未运行检查不得声称通过。

## 数据与上线
本轮已完成本地实施与隔离验收，未改生产数据。实施中迁移需幂等、sqlite一致备份、原ID/来源/快照/法拍资产轮次账目对齐。保留现有人工决定及其他未提交修改；正式部署/迁移/启用由用户另行授权。

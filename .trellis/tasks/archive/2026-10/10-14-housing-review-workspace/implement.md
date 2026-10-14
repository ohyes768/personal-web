# 统一待审核小区与管理页面

## 执行顺序
- [x] 验收任务1交付接口后，由用户明确开始并激活本子任务。
- [x] 测试候选聚合/稳定身份/分期/地址/链式误合并，再实现候选模型/历史副本迁移。
- [x] 实现统一读取/决定/split/restore/summary，覆盖成员冲突、重复提交、Fang一对一和任务1人工锁。
- [x] 接入法拍资产/轮次同步与失败重试、旧入口跳转、Fang候选及独立租金业务入口。
- [x] 实现两个完整列表、详情审核面板、库存/来源统计和移动端布局。
- [x] 定向/完整回归、旧副本对账、隔离桌面/手机三操作与地图刷新验证。
- [x] 写verification.md和spec，移交候选/事务接口供任务3；本子任务不启用自动收录。

## 验证重点
新test_community_review.py/test_community_review_api.py，现有auction_association/auction_list/auction_history、directory_integration及rental_sources；前端community-management/auction-list和新review交互测试。

## 验证命令与环境
后端cwd=backend/housing-map，Windows使用本项目.venv与项目盘独立basetemp：

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp-housing-review-workspace
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
2026-10-14用户明确开始任务2，本轮实施并仅在隔离副本验收。保留原ID/来源/快照/法拍资产轮次及现有人工决定，保护其他并行改动；正式部署/生产迁移/自动收录启用由用户另行授权。

# 住宅收录状态与人工撤销

## 执行顺序
- [x] 用户明确开始后激活本子任务，读trellis-before-dev、community-directory及admission规范；保护现有未提交修改。
- [x] 写准入/锁/迁移与状态转换测试，覆盖江汉路撤销、恢复保锁、重启/采集/新轮次不回收录。
- [x] 实现schema与状态事务、revision/事件、共享读者，隔离数据迁移演练。
- [x] 接入地图/看板有效类型与map_status，保护历史lookup和采集范围、local-ID/TMSF关系。
- [x] 在现有管理页加入最小状态操作与理由标记，验证刷新后地图撤销生效。
- [x] 定向测试后完整后端回归、前端lint/typecheck/node测试/build与隔离浏览器验证。
- [x] 写verification.md及契约更新，提供接口供任务2/3；通过后才进入任务2，生产迁移另行授权。

## 验证重点
新test_community_admission.py/test_community_admission_api.py，现有directory_integration、directory_api、residential_classifier、refresh、auction_history回归；前端community-management交互与手机入口。

## 验证命令与环境
后端cwd=backend/housing-map，Windows使用本项目.venv与项目盘独立basetemp：

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp-housing-residential-admission
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
用户于2026-10-14明确开始任务1，本轮已进入实施与本地验收。迁移需幂等、sqlite一致备份、原ID/来源/快照/法拍资产轮次账目对齐。保留现有人工决定及其他未提交修改；正式部署/迁移/启用由用户另行授权。

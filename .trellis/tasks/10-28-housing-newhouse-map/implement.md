# 实施计划（planning）

本轮仅规划，不task.py start。用户要求实现后加载trellis-before-dev与相应设计/测试技能再启动。此任务为单一跨层体验，暂不拆子任务。

1. [ ] 核实market_state/project/坐标证据的真实存储与投影路径，核对价格字段存在性，确定可选API契约；先写身份、售完、未知、价格隔离与售楼处负例。（A1/A3/A4）
2. [ ] 地图接口与前端类型下发市场身份和已有项目资料，不迁移收录、不触发在线抓价。（A1/A3）
3. [ ] 写三态可见集合、价格文案、附近距离与排序失败测试，再实现纯函数；补1500米阈值及无价/空结果。（A1/A4/A5）
4. [ ] 筛选区增加三段切换；新房点图层、缩放标签/聚合、选中/清理；避免问号占位及建筑生成入口。（A1/A2/A6）
5. [ ] 新房详情、来源可信度、价格口径和附近二手房列表，地图联动与返回锚点。（A3–A6）
6. [ ] 审核二手统计/市场行情/评分及签约挂牌模式，新房与未知不能误入二手专属聚合。（A4）
7. [ ] 1440/375px隔离端到端、后端全量及前端质量门，记录结果与缺字段限制。（A7）
8. [ ] 更新相关spec及任务进度；未经授权不提交、不部署、不改生产数据。

## 重点文件

- backend/housing-map/src/api/routes.py、services/community_views.py、data_loader.py及有效市场状态已有实现（按研究定位，复用不重复写规则）。
- apps/housing-map/src/lib/types.ts、lib/api.ts、app/page.tsx、components/map/BinjiangMap.tsx及新房专用详情/筛选纯函数（按职责提取，避免继续膨胀page.tsx）。
- 后端API/身份/价格测试、前端map筛选与附近比较测试、隔离UIfixture。

## 验证命令

后端从backend/housing-map运行相关测试后执行全量，使用独立项目盘basetemp：

```powershell
./.venv/Scripts/python.exe -m pytest -q --basetemp=.pytest-tmp-newhouse-map-full
```

前端从apps/housing-map顺序运行：

```powershell
npm run lint
npx tsc --noEmit
node --test tests/*.test.cjs
npm run build
```

隔离场景覆盖：有价/无价新房、在售/待售/售完、未知、合法核验/待核验/冲突/无位置/仅售楼处、多点密集、附近有二手/无价二手/筛选后为空、窗口切换及关闭重开。验证中心缩放保留与overlay无残留，不访问生产写接口。

## 开发与回退门

开始前审阅PRD/design默认值，确认已有新房价为空时如实展示。实现后检查筛选、图层、详情、统计四者一致；任何价格/坐标缺失不得伪造。发布不包含数据库或数据批量迁移，新增字段兼容旧客户端。

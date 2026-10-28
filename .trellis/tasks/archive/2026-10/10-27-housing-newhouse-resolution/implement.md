# 实施计划

## 0. 开工前

- [x] 建任务，确认取消人工补全、允许可靠高德主体地址用于收录。
- [x] PRD/设计/实施顺序已收敛，保留原新房采集任务关联。
- [x] 用户审阅后 task.py start，进入实现。
- [x] 实现前读取trellis-before-dev、housing-map索引、collection-pipeline/directory-flow/tmsf-browser/use-review规范及跨层指南；核对Git及并行任务。

## 1. 先建失败用例

- [x] 从真实18项建立脱敏隔离夹具：非住宅缺地址、住宅高德地址齐备、缺主体、无地址POI、身份冲突、预售证不符、网络超时和验证码。
- [x] 证明旧流程仍追证件、可靠高德地址不满足门槛、待地点匹配误入浏览器重试、列表与地图地址判断分裂。
- [x] 保留同数字ID的community/project隔离、人工保护、取消/过期快照回归。

## 2. 统一地址与规则

- [x] 实现共享admission_address投影和独立证据来源；接入eligibility/community_views/地图/详情，搜索所有重复缺地址判断。
- [x] 测同区主体、用途、坐标、地址、身份/证据失效和冲突；不伪造来源字段。
- [x] 独立amap-subject-address-v1开关，关闭时等价旧规则，GET/重启不迁移。

## 3. 简化采集与重试

- [x] 基本采集不追预售证，显式补证调用兼容；明确非住宅停止住宅补证，统一精确类型口径。
- [x] 分开待主体匹配/身份冲突/真正网络失败，调整持久化阶段结果、retryable_sources及历史错误兼容，保留已有事实。
- [x] 基本采集后衔接既有地点/分类，复用预算、互斥、取消和继续入口；不复制查询算法或新增定时服务。

## 4. UI与验证

- [x] 工作台显示基本资料完成/待地点匹配/身份用途冲突/网络可重试/暂停，数量与当前持久化事实一致。
- [x] 地址显示高德主体/官方来源/受保护历史人工来源，不新增人工补资料表单。
- [x] 后端相关测试：newhouse_collection/newhouse_browser/tmsf_browser_protocol/directory_collection/directory_flow/collection_pipeline/community_enrichment/position_status及用途/下游目标测试（930 passed）。
- [x] backend/housing-map使用.venv/Scripts/python.exe -m pytest，专用F盘--basetemp。
- [x] apps/housing-map执行node --test tests/*.test.cjs（117 passed）、npm run lint、npx tsc --noEmit、npm run build。
- [x] 1440px/390px浏览器验证（复用3019生产构建，ui-check.js mock API）：阶段计数4+4+7+2+1+0=18、高德主体地址标注、已自动衔接主体匹配、无横向溢出、无页面错误。
- [x] 生产快照只读演练（address-preview.json）：444项逐项输出，2项excluded→admitted、7项地址来源变化、2项地图变化，active=False待审阅激活。

## 5. 发布与回退

- [x] 输出启用前后收录/排除/待处理及地图/租金/法拍变化预览，审核后再显式激活。
- [x] 按用户授权提交推送，从Git源码构建（提交 fec7431）。
- [ ] 仓库外备份旧镜像、规则和数据库；不再留下阻挡NAS pull的变更。**本轮不部署，留待发布窗口执行。**
- [ ] 仅发布本任务服务，检查健康、规则和只读样本；业务批量写入按审核过的预览执行。**本轮不部署，线上行为未变。**
- [ ] 回退关闭新地址策略重新投影，保留历史事实和后续用户写入，不整库覆盖。**开关 amap-subject-address-v1 保持 active=False，未激活，回退路径可用。**

## 完成门槛

PRD各AC有对应测试/实测证据；规范同步；旧人工决定、二手房挂牌门槛及其他前端改动不回退。提交/部署/规则激活/批量业务写入分别记录实际状态。

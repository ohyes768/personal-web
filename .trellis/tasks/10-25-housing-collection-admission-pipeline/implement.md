# 实施计划

用户已要求规划后直接开发。按顺序执行，先失败测试再改实现；不在本轮直接操作生产数据。

## 1. 新规则与收录矩阵
- [x] 新增新流程版本判定及纯函数；输出 workflow_state 与明确原因。
- [x] 测试住宅双证据、明确非住宅、商住冲突、无地点、手动坐标无类型、人工决定、地址/区域及新房/挂牌门槛。
- [x] 接入 directory_policy，未启用维持旧行为；下游继续共享 admitted 判断。

## 2. 候选身份与地点证据
- [x] materialize 在新模式允许未收录 TMSF 候选，保留重复/分期/锁定/拒绝边界。
- [x] 定位目标从已收录扩至可核对候选；确认事务使用候选资格，不能依赖最终收录。
- [x] 区分精确主体与模糊候选，住宅/非住宅主体一起获取，选定类型与坐标写在同一 POI 证据。
- [x] 回归候选定位后自动分类、多个主体手动确认、商户排除、旧人工坐标保护、取消和快照变化。

## 3. 统一用途判断和展示
- [x] 新模式用途投影只用选定 POI 类型；旧全名用途查询改为选定证据刷新或提示先确认地点。
- [x] API 公开 workflow_state 和选定 POI 分类；增加 pending/excluded 精确过滤。
- [x] 前端更新采集提示、候选定位入口、状态标签和两个来源用途对照，明确人工选位置与确认用途的区别。
- [x] 验证已选主体不受其他商户分类干扰，明确非住宅不批量请求。

## 4. 全量重审迁移
- [x] 添加独立 preview/apply 工具：只读快照与内存模拟、全量影响、明确维护/备份、指纹校验和幂等。
- [x] 所有旧项目统一过新规则；保留历史样本、人工决定、拒绝关系及法拍来源，未通过者退出新采集目标。
- [x] 测试 preview 文件字节不变、stale 拒绝、无客户端启动、人工保护及回滚边界。

## 5. 验证与交付
- [x] backend/housing-map：`.venv/Scripts/python.exe -m pytest tests/test_collection_pipeline.py tests/test_directory_policy.py tests/test_directory_flow.py tests/test_position_status.py tests/test_directory_use_review.py tests/test_use_review_job.py tests/test_use_review_api.py -q --basetemp=.pytest-tmp-pipeline`。
- [x] apps/housing-map：`npm run lint`、`npx tsc --noEmit`、相关 `node --test`、`npm run build`。
- [x] 真实只读低频验证样例：万科城市之光、东和云第；不写线上资料。区分模拟通过、真实查询通过和未部署。
- [x] 更新现有 spec 与任务验证记录；生产 apply 等到具体预览可供用户审阅后再确认。

## 涉及文件

- 后端：directory_policy.py、directory_workflow.py、directory_position.py、directory_position_state.py、amap_directory.py、directory_use_review.py、use_review_policy.py、directory_workflow_routes.py；新增 collection_pipeline.py 与 scripts/migrate_collection_pipeline.py。
- 前端：DirectoryFlowWorkspace.tsx、PositionPanel.tsx、UseReviewPanel.tsx、DirectoryCards.tsx（按实际契约最小调整）。
- 测试：新增 test_collection_pipeline.py，扩充现有目录/定位/用途/API/迁移与前端渲染测试。
- 风险：扩大候选物化可能误建重复身份；确认位置后新用途冲突可能让旧收录退出；API 旧 excluded 口径需保持兼容。各阶段通过版本开关隔离，迁移前只读预览。

# PRD: housing-map 待处理操作筛选与用途确认免证据链接

## 背景

收录目录「待处理」页签目前按 来源用途 / 定位状态 / 用途核对 筛选,与用户实际处理动作(地点链路操作 / 用途拍板 / 补资料)不对应。经讨论确认:改为按「待处理操作」三桶筛选,并把列表中的操作状态升级为标签列;同时取消用途人工确认必须贴证据链接的限制。

三类操作均已实现(地点:查询/确认候选/重查 + 直接不收录;用途:人工确认住宅/非住宅 + 重查;资料:采集任务/手工补地址/确认不收录),本次**不新增任何操作入口**,只改筛选与展示。

## 需求

### A. 待处理页签筛选维度替换

- 移除 pending 页签的「来源用途(property_type)」「定位状态(position)」筛选。
- 新增「待处理操作」单选:全部 / 地点待处理 / 用途待确认 / 资料待补。
- 后端 `GET /directory/workflow/catalog` 新增 `operation` 参数(`position|use|facts`),归桶逻辑与前端 `pipelineStageLabel` 分支一致(所见即所筛)。
- 保留:搜索、区域、「更多」里的用途核对。不收录、已收录页签不动。

### B. 「待处理操作」列

- pending 页签中,「住宅用途核对」表头改为「待处理操作」。
- `pipelineStageLabel`(待匹配地点 / 待确认地点 / 待重查地点 / 未找到主体地点 / 待补主体类型 / 待确认用途 / 待核实用途 / 待补用途资料 / 待核实区域 / 待补资料)从 small 字升级为 badge,pending 的行都显示,不再仅限 `collection_pipeline_version`。
- UseReviewBadge(核对状态)保留为辅助信息。不收录页签该列维持现状。

### C. 用途人工确认移除证据表单

- 前端 `UseReviewPanel` 人工确认表单移除 证据来源 / 证据链接 / 证据说明 三个输入及对应 state,只保留:确认是住宅 / 确认不是住宅 单选、住宅类型选择(确认住宅时)、理由(确认非住宅必填)。提交体只含 revision / decision / property_type / reason,不带 use_evidence。
- 后端 `UseConfirm`:`use_evidence` 改为默认空列表(兼容旧调用方仍可传);`UseEvidence.url` 允许空串。
- 其余校验不变:确认住宅必须选住宅类型;确认非住宅必须填理由。
- 历史人工结论中已保存的证据仍只读展示,不受影响。

## 归桶定义(与前端 pipelineStageLabel 分支顺序一致)

仅对 `workflow_state == 'pending'` 的行分桶:

- **position(地点待处理)**:qualification ∈ {`position_pending`, `position_review`, `position_type_missing`};或 qualification == `type_uncertain` 且 `position.selected` 为空(细分:有 query_history 或 state=error → 待重查;not_found → 未找到;review → 待确认;否则待匹配)。
- **use(用途待确认)**:qualification ∈ {`use_conflict`, `use_uncertain`};或 `type_uncertain` 且 `position.selected` 已选定。
- **facts(资料待补)**:`type_conflict`、`type_missing`、`missing_tmsf`、`identity_conflict`、`identity_pending`、`district_missing`、`address_missing`、`listing_missing`、`region_conflict` 及未知 qualification 兜底。

## 验收标准

1. 后端 pytest 覆盖 operation 三桶各分支(地点类资格、type_uncertain×定位状态组合、用途类、资料类、未知兜底)。
2. 后端:确认请求不带 `use_evidence` 可提交;住宅缺类型、非住宅缺理由仍 422。
3. 前端 `catalog-filters.test.cjs`:pending scope 无 property_type/position、有 operation,选项文案正确。
4. 前端 `position-status.test.cjs` 等现有断言不回归。
5. 后端全量 pytest 通过;前端测试通过、`pnpm build` 通过。

## 非目标

- 不做「补别名再重查」入口(未找到主体地点的行:再查一次或直接点确认不收录,均已实现)。
- 不新增任何操作按钮。
- 不收录 / 已收录页签的筛选与列不动。

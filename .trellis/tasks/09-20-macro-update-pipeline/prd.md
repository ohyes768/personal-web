# 宏观后端更新链路统一：契约测试 + 更新管道化

## Goal

backend/macro 的 18 个 `/update/*` 端点目前各自手写「拉取→清洗→落库→组装响应」全流程（routes.py 3200 行），响应模型 15+ 种且需人工登记 `UpdateResponse.data` 联合类型——spec §7 记录的 DR001「落库成功但响应报失败」bug 即该模式的必然产物。本任务分两批将其收敛为标准化更新管道。

## Background（现状事实）

- 18 个 `/update/*` 端点（routes.py），每端点 80~200 行相似流程，零复用
- 15+ 个 `*UpdateData` 模型字段结构各异；新增端点漏登记联合类型 → 数据已落库但响应 `success=false`（spec §7 已有契约要求，但靠人遵守）
- 覆盖缺口：`/update/eu-bonds`、`/update/jp-bonds` 存在但不在 scheduler 两组 job 中
- scheduler 与前端刷新按钮调同一批端点（触发侧已统一，无需改）
- 查询侧 `query_data_by_tab` 与日频快照直读 CSV 是有意分离（spec §4），本任务不动查询侧

## Requirements

### 批 1：18 个更新端点契约测试（安全网）

- 每个端点至少 1 条契约测试：mock fetcher 返回有效数据 → 断言 HTTP 200、`success=True`、`data` payload 结构正确、存储方法被调用（对齐 spec §7 Tests Required）
- 含边界用例：fetcher 失败/返回空 → `success` 语义正确、不落脏数据
- 全部测试通过且不改动任何生产代码——纯加测试

### 批 2：更新管道抽取与端点薄壳化

- 新增统一管道：`fetcher → validate → save → payload` 四段，差异项（源、清洗规则、目标 CSV、payload 构造）收敛为注册表条目
- 18 个端点瘦身为薄壳（每端点 ~5-10 行，调管道）；按域分小批迁移，每小批全量测试绿后再迁下一批
- 注册表完整性测试：遍历注册表，断言每条目的 payload 类型都在 `UpdateResponse.data` 联合中、每个 payload 类型都有端点与契约测试——漏登记从「靠记性」变为「测试红」
- **响应 shape 对外不变**（各源保留现有 `*UpdateData` 结构），前端零改动；shape 统一为潜在后续任务，不在本任务范围

## Acceptance Criteria

- [ ] 批 1：18 个端点契约测试全绿，覆盖成功与失败语义；生产代码 diff 为零
- [ ] 批 2：18 个端点迁移完成，路由函数平均行数显著下降；删除手写流程后全量测试仍绿
- [ ] 注册表完整性测试存在并能真实拦截（演示：临时删一条登记 → 测试变红）
- [ ] 前端 apps/macro 无需任何改动（响应 shape 兼容验证）
- [ ] scheduler 两组 job 端到端仍正常（可用 scheduler 现有记录/手动触发验证）
- [ ] spec 新增「更新管道」章节，废弃/更新 §7 的手工登记要求

## Out of Scope

- 查询侧（`query_data_by_tab` / daily_snapshot 直读）不动
- 响应 shape 跨源统一（前端配合改动）不做
- eu-bonds/jp-bonds 是否加入 scheduler 排班另行决定（但管道化后加排班成本趋近于零）
- 前端任何改动

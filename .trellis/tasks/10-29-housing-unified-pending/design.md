# 技术设计

## 边界与数据流
新增只读待处理聚合服务与 GET /directory/workflow/pending；读取现有 inventory、auction_tasks、source_reviews，不另建待办表，不修改写入协议。提取并复用 catalog 的小区待处理分类与筛选规则，避免复制后漂移。现有 catalog、summary、auctions 及租金接口保持兼容。

聚合行包含 key、community_id（可空）、name、address、district、issues；法拍来源标识保留在 issue.auction.id；issue 包含 kind（admission/auction/rental）、reason、action、原业务定位标识。小区 key 为 community:<id>，法拍为 auction:<source-id>。只允许相同已确定 community_id 合并。小区详情点击后从原接口获取最新资料；法拍携带当前聚合快照 revision，写入由原接口验证新鲜度；租金由探查组件读取最新探查状态。不绕过任何原写入校验。

## 查询与数量契约
参数：q、district、kind、rental_status、include_skipped、适用的小区 operation/use 筛选、page、page_size。枚举和值约束由 API 明确定义；不适用参数不参与筛选。地区从目录资料或法拍自身事实取得，无可靠地区的法拍仅在全部区域出现，不猜测归属。
响应：items、total、page、page_size、counts（all/admission/auction/rental）、default_pending_total。counts 基于搜索及区域、默认未跳过集合，在 kind/status 和分页前计算；default_pending_total 为全局默认待办行数供顶部使用，不受列表临时筛选影响。分类数量按含该类 issue 的行数计，all 为去重后的行数。旧 summary.pending 继续保持旧业务语义，新增 unified_pending，不覆盖旧字段。
顺序：读取完整候选 → 构造 issues → 去除非人工租金待办 → 按真实身份合并 → 搜索/地区 → 分类计数 → 事项/适用状态过滤 → 稳定排序 → 分页。稳定排序按需人工确认优先，再按名称及 key；租金内部待选择、查找失败、未找到优先级固定。通过共享函数确保顶部与清单默认口径一致。

## 交互组织
DirectoryFlowWorkspace 保留外层模式 admitted/pending/excluded。新增 PendingWorkspace 负责统一工具栏和列表，复用 CatalogFilters 的适用条件规则。租金清单组件提取可复用的详情交互，不嵌入整套标题和筛选；保留其他调用点兼容。小区详情与 AuctionPanel 延续现有写操作，幸福里确认复用 XingfuliProbe。多事项行提供逐项按钮，弹窗只处理所选事项。
initialSource=laipai 映射至 pending + kind=auction；定位核对保留原 focusPosition 路由。动作成功及轮询任务完成时统一失效刷新；请求取消或版本保护避免旧响应覆盖新筛选，过滤后页数越界回退。

## 兼容与回滚
不迁移数据，不复用 admission_state 表达租金状态。保护旧接口、旧 RentalAssociationReview 调用点及 pipeline 开关边界。后端新增能力部署后再切前端；回滚前端即可恢复原入口，新增接口可暂留。跨源读取可能存在短暂快照差异，写入继续由原互斥与 revision 校验保证；成功后重新加载。

# 设计

DirectoryFlowWorkspace 保留单一 mode：admitted/pending/excluded 归审核，rental/auctions 归维护；由 mode 派生主 Tab，避免维护与审核状态错配。主 Tab 切换复用 changeMode，清理详情、分页、多选和不适用筛选。审核继续 CatalogTabs/CatalogFilters/CatalogTable，维护采用带标签的原生事项 select，再渲染原 RentalAssociationReview 或法拍列表。

laipai 初始 mode=auctions，天然选维护；focusPosition 的 mode=admitted 回审核。各清单继续使用原请求和计数，复用请求取消、revision 写入校验及任务刷新机制。此次不增加后端接口，无数据迁移；回滚只需恢复本次前端改动。

取舍：保留原五个并列入口不符合两个主 Tab 的要求；恢复统一聚合会再次混淆审核与维护。采用两主 Tab 加各自原状态/事项选择，在最小改动内保留原处理逻辑。

三状态补充：CommunityRegistry新增reopen-review/complete-review动作，在现有准入事务中校验revision、活跃身份及v2模式。重新审核保存pending/manual、auto_review_locked及review_requested标记，directory_policy映射为workflow=pending、qualification=manual_review，区别于人工排除；不改业务来源。完成审核清除复核标记和锁，由原eligibility重算。人工用途确认允许本复核锁，显式确认后替换为用途决定；其他人工排除锁继续保护。新工作流路由复用此事务，旧resume不变。前端复用一组动作组件用于列表/详情，阻止重复点击、过期版本，不新增强制收录按钮。

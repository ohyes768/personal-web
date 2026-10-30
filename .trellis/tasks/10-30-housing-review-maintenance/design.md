# 设计

DirectoryFlowWorkspace 保留单一 mode：admitted/pending/excluded 归审核，rental/auctions 归维护；由 mode 派生主 Tab，避免维护与审核状态错配。主 Tab 切换复用 changeMode，清理详情、分页、多选和不适用筛选。审核继续 CatalogTabs/CatalogFilters/CatalogTable，维护采用带标签的原生事项 select，再渲染原 RentalAssociationReview 或法拍列表。

laipai 初始 mode=auctions，天然选维护；focusPosition 的 mode=admitted 回审核。各清单继续使用原请求和计数，复用请求取消、revision 写入校验及任务刷新机制。此次不增加后端接口，无数据迁移；回滚只需恢复本次前端改动。

取舍：保留原五个并列入口不符合两个主 Tab 的要求；恢复统一聚合会再次混淆审核与维护。采用两主 Tab 加各自原状态/事项选择，在最小改动内保留原处理逻辑。

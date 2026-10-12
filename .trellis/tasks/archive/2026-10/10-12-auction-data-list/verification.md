# 验证记录（2026-10-12）

## 已完成
- 独立法拍页签、累计轮次列表、搜索/状态/关联筛选、分页、物业事实/来源展开、地图定位、成功刷新联动、命中条数文案。
- 后端测试先观察overall_total缺失的失败，再实现后通过；法拍目标测试21通过（test_auction_list、test_auction_history、test_auctions）。
- 前端先观察新组件不存在的失败，再实现；法拍SSR测试4通过。pnpm lint、tsc --noEmit、pnpm build通过。
- 最终前端所有*.test.cjs共28项通过，包含并行租金模块既有测试；类型检查复跑通过。
- 后端全量：257通过、5失败、2既有依赖弃用警告。失败均在并行租金模块test_rental_api.py：detail_pagination_server_side、detail_source_url_domain_whitelist、detail_area_band_filter_scopes_samples、refresh_delete_cancel_and_conflict、main_app_registers_rental_routes。未修改该模块，未声称全量通过。

## 真实页面验证
- 当前存储已累计7条（不是用户此前本次采集的4条）；页面累计7、未关联筛选2。未关联天寓/江滨花园保留可读，没有定位按钮。
- 搜索倾城命中对应记录，来源成交476万元、149.3㎡、31882元/㎡；未成交记录成交价/单价暂无。
- 房源卡片地图查看进入10001742顺发倾城之恋并展开详情，地图聚焦200米级；已有法拍成交1和租金页签保留。
- 390×844布局卡片单列、价格两列，物业事实纯文本可展开；正文宽度384.8px（包含滚动条空间），无新增横向溢出。
- 停止本地后端后显示不可用及重试；恢复后点击重试累计7条恢复。
- desktop.jpg、mobile.jpg保存界面证据。
- 开发缓存曾未包含新增CSS，清理已核对路径的.next/dev后重新生成恢复；业务代码无需针对缓存变更。

## 验证边界
未重新运行全量采集；成功采集刷新版本联动经代码审查，取消/失败保持旧存储沿用既有job测试。真实数据不足20条，分页及多轮次口径由后端测试覆盖。未部署、未提交推送。

## 收尾
已将列表查询契约、轮次计数及关联规则更新到housing-map-auctions.md。任务代码待提交，按finish-work约束暂不归档；保留其他租金、红利等工作流变更。

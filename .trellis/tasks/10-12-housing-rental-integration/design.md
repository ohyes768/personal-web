# Technical design

## Data boundary
CLI输出保持为原始挂牌样本。新增 rental_reference 服务负责映射、筛选、聚合与发布，不将租金逻辑塞进地图评分或已有售价快照。
运行数据放在后端data卷：rental_community_mappings.json、rentals/runs/<run_id>/（样本+报告+manifest）、rentals/current.json（已发布版本指针）。先完整写批次再原子切换指针，API只读取已发布版本。保留最后成功的小区数据；部分失败时不把历史有效样本变为空。
映射台账字段：source、source_community_id、community_id、source_name、source_address、verified_at、status、notes。现有合并小区别名按内部展示ID归属，避免dropIds数据丢失。

## Statistics and quality
以最新成功快照统计，不将多日相同房源重复计入样本。先按来源ID去重，再标记相同小区/房型/面积/租金/楼层的疑似重复（无可靠房屋ID时不能自动证明同套）。疑似重复进入审核，默认不参与样本数量。详情未核验候选仍可明细展示但不进入统计。
按房型、面积段计算单位面积月租中位数，不能用总月租中位数除以面积中位数。样本>=3才输出参考。IQR不自动剔除真实高价户型，疑点标记并保留排除理由。
参考年化毛收益率(%) = unit_rent_yuan_m2_month * 12 / sale_unit_price_yuan_m2 * 100。
月租售比1:N中的N=sale_unit_price/unit_rent；在API输出数值，不存格式化字符串。售价取现有load_price_snapshots策略，保留口径和日期，不重复实现过期签约价规则。
租金快照超过30天标记过期，过期明细仍可看，但不输出当前收益率、不参与收益率排序；日期按UTC时间差判定。

## Query API
新建src/api/rental_routes.py并在main.py注册：
- GET /api/rentals/summary?area_band=...&bedrooms=...：按内部community_id返回统一口径的摘要，供看板独立加载。
- GET /api/communities/{id}/rentals?area_band=...&bedrooms=...：分组汇总+分页明细+排除理由，未知ID与未映射明确区分。
对外路径由nginx映射为/api/map/...，遵循现有success/data envelope。
响应显式availability（available/unmapped/no_samples/insufficient_samples/stale/source_failed）、sample_count、excluded_count、rent_reference、sale_reference、yield_estimate、captured_at及来源链接。允许旧数据可用与最近抓取失败同时存在。
样本链接只允许预期https来源域。缺失和非有限数值保留null或拒绝，不出现NaN/Infinity。

## Frontend
CommunityDetailTabs新增rental标签；新建CommunityRentalReference组件及lib/rental-types.ts。切标签后加载，AbortController取消旧小区请求；明细显示挂牌月租/面积/户型/来源链接，默认有效候选，可查看排除样本。
DashboardPage独立加载摘要；全局统一房型+面积选择后渲染三列，避免隐式任选最高收益组。推荐默认90至<144㎡、全部房型；全部房型会合并该面积段的合格整租样本重新统计，不能平均各房型中位数。详情同时显示房型分布，API与看板使用同一算法。
不新建第四主标签；原市场行情保持区域挂牌参考的定位。

## Web refresh — user confirmed
用户已选择网页“更新租金”按钮，不再采用只读CLI方案。
- GET /api/rentals/refresh：返回job_id、running、phase、total_communities、processed_communities、current_community_id、pages_fetched、details_fetched、success_count、failed_count、started_at、finished_at、last_success_at、errors（有上限+总数）、result。
- POST /api/rentals/refresh：无任意URL参数，后端从已核验台账确定范围；202启动，409已有任务，422无可采集映射。默认每小区最多10页、详情全部验证，请求间隔2秒、超时20秒；限制以服务配置保存。分页到上限标记不完整，保留旧小区版本。
- DELETE /api/rentals/refresh：设置取消事件，状态变为cancelling；线程在每次请求/等待及发布前检查，等待用event.wait而非不可取消sleep。进行中的HTTP请求在超时内结束，无活动任务409。
- 独立rental_refresh服务复用现有法拍asyncio.to_thread、threading.Event与文件锁模式，但job字段和锁路径独立；CLI发布与网页共享锁。服务关闭设置取消并等待线程退出；服务重启将未结束job标为interrupted并安全恢复锁，不能仅凭锁文件年龄删除活锁。
- 任务状态写入独立job文件，网页重新打开可GET恢复。请求进度与成功小区快照分离；更新未完成仍读取旧指针。
- 小区完整采集且详情全部成功才合并该小区数据；明确空页视成功空快照；截断、列表/详情失败保留旧快照。全部失败不切指针；部分成功发布混合版本，并逐小区保留采集日期和失败状态。取消任何阶段不发布。
- 页码/详情计数不假装总体百分比；主要进度为已处理小区/总小区，明细请求数辅助展示。
- 按钮放数据看板工具栏，在“更新房价”旁；小区租金标签展示相同job状态并提供“更新租金”入口（更新全部已映射小区，文案明确范围）。共用一个前端hook，运行时按钮禁用并显示取消操作，每2秒轮询；终态重新请求摘要与当前详情，卸载清理轮询和AbortController。
- 不新增定时任务、自动跟踪或通知；沿用现有刷新API访问边界，不创建新外部通信。

## Rollout
先核验风雅钱塘、璞悦湾、东方郡的来源ID和地址，完成三个小区映射后落地和明细空态；样本不足时不强行展示收益率。逐步扩充映射；不要求覆盖所有小区后才上线。移除租金路由/组件可回退，现有价格数据无迁移。

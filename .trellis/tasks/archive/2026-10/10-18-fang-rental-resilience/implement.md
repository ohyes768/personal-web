# 房天下租金采集优化实施计划

**目标：** 减少请求量，风控后跨轮暂停，保持快照与统计口径准确。

**架构：** 共享请求策略和独立详情缓存接入全部房天下入口；刷新编排区分真实采集、复用和暂停，API/UI 兼容扩展。

**技术栈：** Python、curl_cffi、OS 文件锁、原子 JSON、pytest；现有 Next.js/TypeScript 租金更新组件。

## 1. 实施准备
- [x] 规划审阅后 task.py start 本目录，载入 trellis-before-dev、housing-map backend index、rental-sources、rental-reference 和 Windows testing-environment 规范。
- [x] 检查 git diff，保留定位、轮廓和 UI 等其他任务的未提交改动。

## 2. 请求策略（R1/R4/R5）
- [x] 新增 tests/test_fang_request_policy.py，用假时钟测试共享 5 秒间隔、取消、重定向计数、持久冷却三级升级、重启保持与有限超时重试；先运行确认失败。
- [x] 新增 src/services/fang_request_policy.py，接入 FangClient，使用独立稳定锁路径和原子状态文件。
- [x] 扩展 test_fang_rentals.py/test_fang_rentals_run.py，证明详情首次挑战停止后续请求、未知跳转仍拒绝；修改 fang_rentals.py 对应控制流。

## 3. 详情缓存（R2）
- [x] 新增 tests/test_fang_detail_cache.py，覆盖 7 天边界、失败不写、来源隔离、损坏文件与字段白名单；先运行确认失败。
- [x] 新增 src/services/fang_detail_cache.py，接入正常抓取、sources.discover、directory_collection.fang_names 和 CLI；保留独立验证时间。
- [x] 测试连续两轮请求次数、价格更新和房源下架不被缓存影响，缓存命中满足原有统计准入。

## 4. 编排与发布（R1/R3/R7）
- [x] 扩展 test_rental_refresh.py/test_rental_association_flow.py：已有来源优先、搜索预算 5、新绑定下一轮采集、6 小时完整快照复用及来源变更失效。
- [x] 扩展存储测试：混合网络成功/复用/失败不丢小区，全部复用不移动 current 指针、不改原时间。
- [x] 修改 refresh.py/association.py/storage.py，实现显式保留集合，继续保留取消、编辑互斥和成员重查。

## 5. 状态与页面（R6）
- [x] 定位 RentalRefreshJob 类型和更新组件，新增可选 request_count/detail_cache_hits/reused_communities/cooldown_until/deferred_count，API 序列化与旧任务兼容。
- [x] 补 API/前端测试：旧字段缺失、冷却时间、缓存复用与真实成功分别展示；修改现有更新组件。

## 6. 验证与收尾
- [x] 使用 backend/housing-map/.venv/Scripts/python.exe 运行房天下、策略、缓存、租金刷新/存储/统计/API/关联、directory collection 相关 pytest；独立 --basetemp 放项目目录，全部 HTTP 离线注入。
- [x] apps/housing-map 运行租金组件 Node 测试、lint、TypeScript 检查；UI 变更做桌面和移动预览。
- [x] trellis-check 核对 R1—R7；更新采集与租金参考 spec 的默认值、缓存、状态契约，记录验证结果。
- [ ] NAS 上线后进行少量真实列表与一条详情烟测；本轮未部署、未触发生产采集、未提交或推送。

## 风险检查
文件锁与取消、状态文件原子替换；缓存不能覆盖动态字段；混合发布显式保留复用小区；phase 与前端枚举保持兼容。

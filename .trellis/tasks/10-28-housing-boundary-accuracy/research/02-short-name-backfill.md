# 短名称与两个小区轮廓补齐（2026-10-28）

用户明确要求“修名字匹配，补上两个，开干吧”。本轮在既有in_progress任务内补修，范围为钱江彩虹城10001734、长虹苑20096840；不改其他会话的新房地图工作。

## 已复现与修复

- 原identity_match最短四字，拒绝长虹苑同名与彩虹城包含匹配，退回建筑碎片（约0.10/0.53公顷）。新增失败回归7项明确复现后实施。
- 两字以上非通用专名允许完全一致；包含至少三字，通用词和两字局部包含拒绝；空间/远区/歧义校验继续有效。ALGORITHM_VERSION v1→v2，旧ready候选不能继续复用。
- 加固定离线fixture包含两处查询窗口。估算+坐标测试59项通过；服务层工作流测试24项通过（4项HTTP/token测试未执行）。HTTP TestClient挂起经faulthandler定位到Windows asyncio的socketpair/accept初始化，未声称全量通过；未修改无关框架测试。

## NAS 发布与应用

- 已检查NAS仓库源码与原运行容器一致，目标文件原先干净；仅同步boundary_estimate.py，标准docker compose build及up --no-deps --no-build发布后端。镜像构建成功，健康接口ok。
- 发布前确认无在途估算任务，SQLite一致备份：/app/data/boundary_workflow.before-short-names-20261028T091615Z.sqlite3。原源码备份在NAS /tmp/housing-boundary-estimate-before-short-names.py。
- 长虹苑：正常公开生成接口生成候选fbfdf35bb94f4bce84dea43d2c5b3acc，1.64公顷、5建筑面+1住宅面；校验定位包含、与way 544075643的IoU=1.0后按用户指令通过apply接口保存。operation_id=short-names-changhong-0040711019df411391371ec2eddda49c，保存后has_visible_boundary=true，可撤销。应用时间UTC 2026-10-28T09:17:49Z（北京时间17:17:49）。
- 钱江彩虹城：算法生成11.60公顷主区（way 589380851），但NAS中“彩虹城”已合并到10001734，用途门因120300大类不足而暂停收录，首次公开生成接口404。解释后用户明确回答“是，恢复展示并补轮廓（推荐）”。先一致备份注册库/app/data/community_registry.before-caihong-confirm-20261028T092039Z.sqlite3，再通过既有use-review/confirm接口按住宅确认（revision 1→2，保留人工审计记录），没有改规则或直接写表绕过。
- 钱江彩虹城随后通过公开生成接口产出候选d06e205e4d044ae39f390190997063bb，29建筑面+1住宅面、11.60公顷、无低置信警告。定位包含且与way 589380851的IoU=1.0；通过apply保存，operation_id=short-names-caihong-2943af0b00c74d049b8ab28cd1b11263。UTC应用时间2026-10-28T09:21:39Z（北京时间17:21:39）。
- 当前主区包含一期闻涛苑、二期水云居/江月园等定位，不含单独的浪琴轩面；彩虹豪庭另有独立条目。不自动拼接分期。
- NAS其他会话同时改动合并/收录，统计已从最初158收录/12缺口变为发布时156收录/10缺口；长虹苑应用后156收录、147展示、9缺口。该变化不全部归因于本修复。
- 最终GET /api/communities：157收录、148展示、9缺口；两目标均返回boundary_source=osm-building及一个有效环；GET各自boundary-workflow均has_visible_boundary=true且revertable存在。未改基础轮廓文件；未自动合并浪琴轩或彩虹豪庭。

本地及NAS源码未提交；用户本轮未要求commit/push。后续须同步提交，避免NAS下次拉取时覆盖或产生未提交冲突。

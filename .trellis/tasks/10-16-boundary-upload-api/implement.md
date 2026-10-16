# implement — 轮廓上传接口与前端展示

前置:工作区可能有其他会话的未提交改动,动工前 `git status` 核对,只提交本任务文件。

## 步骤

1. **服务函数骨架**:`services/boundary_import.py` 的备份+原子写函数;`HOUSING_ADMIN_TOKEN` 读取。
   验证:单测 tmp 目录写入/备份轮转(>5 份删旧)。
2. **路由 + 鉴权**:`boundary_import_routes.py` 挂载;401/503 用例。
   验证:pytest 通过。
3. **校验链**:四条校验逐条实现,拒绝响应带 cid+原因。
   验证:pytest 各拒绝路径 + 合法路径。
4. **落盘合并 + 幂等**:同 cid 覆盖、_meta.sources 追加去重。
   验证:pytest 写入内容断言 + 重复上传不重复。
5. **前端展示**:BinjiangMap.tsx 白名单 + 虚线;types.ts 类型放宽。
   验证:本地塞一条 osm-building 样例数据,地图页目检虚线;`pnpm build` 通过。
6. **全量回归**:后端 pytest 全量 + 前端 build;与脚本任务联调(在该任务端到端步骤)。

## 检查点

- 第 3/4 步(校验与落盘)是安全与数据完整性重点,review 后再进前端。
- 不得改动既有轮廓数据(142 个 osm 条目)的内容——测试断言只增不改。

## 回滚点

- 路由未挂载前任何失败:删新文件即可。
- 已落盘脏数据:`data/boundaries-backup/` 最新备份还原。

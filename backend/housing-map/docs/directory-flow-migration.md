# 住宅名单流程上线与旧资料处理

本流程的执行对象是服务实际 DATA_DIR 内的 community_registry.sqlite3。不是仓库静态 JSON，也不是前端缓存。仅部署代码不会重算或删除生产名单；在显式迁移前，新管理页显示未启用并禁用采集按钮，旧地图按原规则运行。

## 操作顺序
1. 先验证新镜像/代码。保留旧镜像用于回滚。
2. 准备维护窗口，停止 housing-map 后端（包括定时调度）以及所有采集 CLI；确认没有其他进程写这个数据卷。迁移前不要运行普通应用入口，避免启动时隐式初始化改变预演数据。
3. 使用有权限读取真实数据卷的新代码运行下列 preview。`--plan` 和 `--backup-dir` 必须持久保存在 DATA_DIR 外，不能只存一次性容器 /tmp。
4. 把预演变化、人工冲突、历史-only小区及业务关联影响给用户核对；此任务的实施授权不包含生产迁移授权。
5. 得到具体报告的确认后，在同一停写窗口执行 apply。若快照变更，重新 preview，而不是绕过核验。
6. 启动新服务。验证已收录、不收录（条件不符/资料待补）、法拍待关联，检查地图、租金映射和法拍历史；再由用户按需独立点击四个采集按钮。

以下以本地虚拟环境为例，参数路径替换成实际部署位置；容器内可以直接用 python。容器须挂载同一生产数据卷及外部持久备份目录，并覆盖默认入口直接运行脚本，不要先执行启动导入脚本。

```bash
.venv/bin/python scripts/migrate_directory_flow.py --data-dir /实际/data --plan /持久备份/plan.json

.venv/bin/python scripts/migrate_directory_flow.py --data-dir /实际/data --plan /持久备份/plan.json --action apply --backup-dir /持久备份/before-directory-v1 --maintenance
```

apply 保存 registry 一致备份、业务JSON/JSONL/GeoJSON和其他SQLite备份，写 plan.json 与 receipt.json，事务内设置 directory_flow_version、停用旧自动审核并创建符合条件的TMSF主档。旧主档用途证据初始化仍保存在历史admission/events；当前不收录原因来自有效TMSF资料。人工排除、删除、拒绝、关联以及房价、租金、法拍历史不会被清空。旧Fang/高德孤立主档退出住宅业务视图但原始记录保留。已移除的高德来源不会恢复。

## 回滚
只允许在停写窗口且迁移后没有新数据时整库回滚；工具核验完整数据库/业务文件指纹，有新写入就拒绝，防止丢掉迁移后的人工决定或采集结果。

```bash
.venv/bin/python scripts/migrate_directory_flow.py --data-dir /实际/data --plan /持久备份/plan.json --action rollback --backup-dir /持久备份/before-directory-v1 --maintenance
```

回滚成功后再切回旧镜像启动。若已有新数据，保留当前库，依据迁移事件和备份逐项恢复，不做强制整库覆盖。

## 未完成采集
若停机前仍在采集，先正常取消/等待结束。若任务崩溃留下running状态，先让原服务恢复中断状态再停写并重新预演。不要手工清除running标记骗过检查。高德、租金和透明售房网任务支持持久化中断/取消，法拍进程退出后仍保留原始轮次文件。

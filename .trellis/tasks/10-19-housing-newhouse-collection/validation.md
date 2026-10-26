# 新房浏览器实现验证（2026-10-26）

## 已实现

独立 Playwright worker、内网受限目标协议、主服务显式开关、任务会话复用/关闭/空闲回收、请求限速/有界等待、可见验证码暂停、跨会话15分钟冷却、客户端失败后不再请求；共享新房详情解析和同项目预售证完整坐落补证；24小时部分详情缓存；地址补证失败保留已验证用途、旧地址及错误；批量暂缓统计及单次暂停摘要；只读来源证据预览 CLI。

没有修改收录规则、价格/租金算法、人工决定或生产数据库。工作区另有收录流水线/高德复核及前端改动，不属于此次浏览器交付，未回退或代为提交。

## 离线检查

- 最终全量命令：在 backend/housing-map 下，`PYTHONUTF8=1`，`HOUSING_DATA_DIR` 指向专用 `.pytest-tmp-browser-seed`（仅复制随仓库分发的公共 JSON/JSONL/GeoJSON，不带生产 SQLite），`.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.pytest-tmp-browser-final-gate`。
- 结果：**834 passed，2 个既有 Starlette/anyio 弃用警告，44.54 秒**。该计数为验证时的完整工作区测试总数，包含并行任务已有测试。
- 新增测试：test_newhouse_browser.py、test_tmsf_browser_protocol.py、test_newhouse_preview.py。记录了先失败、实现后通过的证据，包括错误项目/证号、取消、缓存、售完优先、旧地址保留、暂停后不请求、全暂缓不能显示成功及原库字节哈希不变。
- Windows 沙箱内 asyncio 在 `_fallback_socketpair -> accept` 卡住；faulthandler 已定位。允许本地套接字的外部测试环境跑通，无产品代码规避或测试跳过。最初空数据目录造成的市场参考/交通快照两项失败，改用隔离公共种子后消失。
- `git diff --check` 通过；Compose 用 NAS 已有 `.env` 仅做 `config --quiet` 及 `--services` 校验通过，包含 housing-map-backend / housing-map-frontend / housing-map-browser。未输出环境变量值。
- 未改前端文件，未为此浏览器任务运行前端构建；前端当前改动属于并行任务。

## NAS 实测

独立镜像 `housing-map-browser:verify-20261025`，image ID `sha256:f84b00d2af232a931d574fe8722fd1c323fc866bc9db248f926dfa02874ee3be`。

Playwright1.59.0 / Chrome for Testing147.0.7727.15，uid10001，1CPU/1GiB内存限制，256MiB shm，无生产数据卷、无发布宿主机端口。镜像约969MB，空闲容器约92.93MiB；未测峰值。首次下载官方 CDN 极慢，改用区域镜像下载同版本公开浏览器文件后构建成功。未采用 stealth、代理换 IP、验证码求解或用户个人 profile。

预览 CLI 使用线上现有后端镜像作为依赖环境，只读挂载 `housing-map-data:/input:ro`，覆盖本任务的三个读取模块后运行；登记库只以 mode=ro 打开并复制到临时目录；没有 ingest/enrich/admission/定位调用或生产写权限。

### 三个住宅样本

2026-10-26 00:08（北京时间）取得三条完整来源证据，6 个页面请求（各主页+一个预售证）、复用一次会话，结束执行 close。无人工操作。

| 项目 | 用途/状态 | 预售证 | 完整实际地址 |
| --- | --- | --- | --- |
| 春来晴翠园 | 住宅 / 在售 | 202600601 | 东至规划道路，南至零磁谷街绿化，西至浦沿路绿化，北至回龙庵街。 |
| 月澜雅颂里 | 住宅 / 在售 | 202600583 | 东至文水河规划绿化，南至生地街，西至浦沿路绿化，北至规划绿化 |
| 泊玺骏庐 | 住宅 / 在售 | 202600599 | 东至规划占家湖路，南至最葵园南侧支 路，西至空地，北至孔家里 |

原始证据：[三个样本预览](./research/2026-10-26-preview-three.json)。三者均为来源证据齐备的新候选，未因此在生产创建/收录小区，缺少高德定位不在此次补录中处理。

### 19 条候选与真实验证码

按登记库来源 ID 顺序做只读预览。世茂栖棠誉湾身份/区域未通过严格核对，拒绝采用；领界大厦取得明确“非住宅”和完整地址；潮上中南银座取得“非住宅/尾盘”，但其预售证请求出现可见验证码。程序停止访问余下16项，保留已有字段。

[初版全量原始报告](./research/2026-10-26-preview-all-initial.json) 当时仍将后16项记作 fetch_failed（总计17个 fetch_failed）；它们没有真的发出页面请求。发现后已修复为 deferred，并新增冷却开始/中途触发的回归，不更改原始实测文件来美化结果。明确“非住宅”的来源现在在预览中独立标记 non_residential，不更改主业务准入类型集合。

修复后在同一 worker 冷却期内再做只读预览，结果：[冷却状态预览](./research/2026-10-26-preview-cooldown.json) **19 deferred**；worker 只收到一次 `/page`，返回409 paused，随后一次 close，没有再访问 TMSF。

这证明暂停机制有效，也意味着不能承诺19项一次性全部补齐。身份不一致、缺证件/地址、明确非住宅和验证码暂缓必须分别处理。

### 资源清理

验证 worker 健康检查为 healthy、会话已关闭。临时预览容器运行结束自动删除，worker 临时容器也已 stop/rm；镜像和 `/tmp/housing-browser-20261025` 下的构建/报告材料保留。生产 housing-map-backend/frontend 未重启，生产登记库未写入。

## 上线与回滚边界

当前为**代码与隔离验证完成、尚未上线**。原 PRD R7/发布设计规定“生产执行另行授权”，因此不以只读预览代替生产补录许可。

确认上线时：

1. 核对并行任务的发布状态与线上采集是否运行；只发布本任务读取模块、worker 及环境配置，不能顺带覆盖他人的收录规则/UI改动。
2. 保存当前后端镜像和 Compose 配置；部署内网 worker，健康后发布主后端 `HOUSING_TMSF_BROWSER_URL=http://housing-map-browser:8097`。没有启动采集任务或数据库迁移的脚本。
3. 验证两个服务健康、名单 GET 正常；由显式启动的采集/更新资料使用新能力。批量写入生产名单另按审阅过的当前规则/预览执行。
4. 回滚只需恢复原后端镜像并移除浏览器 URL 配置、停止 worker。新增来源证据/缓存是 additive JSON，旧代码可忽略；不整库恢复、不覆盖用户后续写入。

协议及字段契约见 `.trellis/spec/backend/housing-map/backend/tmsf-browser.md`。此次未 commit/push、未归档任务。

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

## 2026-10-27 加载超时与区域模板修复验证

- 本地先复现 10 项失败（34 项通过），实现后补充重定向拒绝、Playwright 风格 TimeoutError 和探针断连测试，相关 8 个测试文件共 **125 passed**，2 条第三方依赖弃用警告。命令在 backend/housing-map 下使用 `.venv/Scripts/python.exe -m pytest tests/test_newhouse_browser.py tests/test_tmsf_browser_protocol.py tests/test_newhouse_collection.py tests/test_newhouse_preview.py tests/test_directory_collection.py tests/test_community_enrichment.py tests/test_tmsf_property_type.py tests/test_tmsf_fetcher.py --basetemp=.pytest-tmp-browser-verified -q`，启用 PYTHONUTF8=1；本机回环 HTTP 需沙箱外权限，避免 WinError 10013。最后摘要分支整理后再次复验协议测试 25 passed。
- 用户明确批准将本次源文件上传至 NAS 临时目录 `/tmp/housing-browser-fix-20261027-01a17b23`，仅供只读样本验证。原上传曾被自动审批拒绝，批准后上传成功。
- 使用已有浏览器镜像启动 `docker run --rm` 隔离容器，挂载临时 worker、限制 1GiB/1CPU/256MiB shm，无业务卷。单次读取世茂栖棠誉湾 `property_33_1266434254_infoUpgrade.htm`，7.42 秒返回正文（106387 字符），未遇可见验证码。HTML 仅保存临时目录用于离线解析，未打印/保存 Cookie。
- 在另一个 `--rm --network none` 后端临时容器中，对同一份 HTML 比较：原解析器报“新房详情页面无法确认目标项目和区域”；新解析器通过，得到 `property_type=住宅`、`project_sale_status=待售`、`market_state=new_house`、`address_district=滨江`、`address=滨江区坚塔路与新浦路交叉口`、`address_evidence_kind=tmsf_project_detail`。未请求预售证或其他项目。
- 两个临时验证容器均自动删除。NAS 临时源文件、脚本和公开页面 HTML 保留用于复查。生产 housing-map 前后端及 browser 未重建/重启，后端和 browser 仍 healthy，未调用采集/补资料写入接口，未挂载生产数据卷。
- 结论限于此样本真实读取及新旧解析器对照，不承诺 19 个项目全部成功；生产仍使用旧版本，需要另行发布后才能让界面重试使用修复。

## 2026-10-27 生产发布完成

用户明确要求“发布后端和浏览器服务”。发布前 NAS/本地均为 `9aa6abc`，NAS 相关源码与 Compose 无未提交修改；目录采集、定位、用途复核、租金和法拍均未运行。

- 备份位置：`/home/ohyes768/personal-web/backups/housing-browser-fix-20261027-01a17b23`，包含旧 Compose、4 个旧源码文件和 images-before.txt。旧镜像分别保留为 `personal-web-housing-map-backend:rollback-browser-fix-20261027` 与 `personal-web-housing-map-browser:rollback-browser-fix-20261027`。
- 仅同步 `src/browser_worker.py`、`src/services/tmsf_browser.py`、`src/services/tmsf_property_type.py`、`src/services/directory_collection.py`；使用 `docker compose -f docker-compose.nas.yml build housing-map-backend housing-map-browser` 构建，再依次 `up -d --no-deps --no-build --wait --wait-timeout 45` 更新 browser、backend。未更新前端、删除卷或处理无关 orphan 容器。
- 后端生产镜像：`sha256:32f12d87068e348685753303debda9a5b285cd5f77b4694274da41ca1e224ab9`；browser：`sha256:0c9124d553250b2955068d755b49516bc5183ae04f27f555f967f486e2ab5ec8`。两服务均 healthy。
- 从正式后端通过正式 browser 只读调用 `fetch_project_facts_by_id`，世茂栖棠誉湾 5.87 秒通过，取得住宅/待售/滨江及完整实际地址。仅输出结果，不 ingest/enrich，不写业务资料；检查 API 健康且 collection_running=False。批量失败项需用户在界面自行发起重试。
- 回滚时：将两个 rollback 标签重新 tag 为对应不带标签的 Compose 镜像名，恢复备份的 4 个源码文件，再分别用 `up -d --no-deps --no-build --wait` 更新两个服务。不要运行 build（会重新构建当前源码），不要删除/覆盖生产数据卷。Compose 本次未修改，无需改环境变量。
- 本地修复尚未 commit/push；后续发布前需保留或正式提交本次修复，避免旧源码重建覆盖。

## 2026-10-27 动态节点二次修复

- 用户重试后，世茂栖棠誉湾已成功，领界大厦触发 `Locator.text_content: Timeout 30000ms exceeded`，而非此前的 Page.goto 超时。根因是 readiness 先 count 再 text_content，目标站点重建节点时，两次调用之间存在竞态；原稳定 fake 和单页实测没有覆盖此情况（隐含假设 + 测试缺口）。
- 改为一次 `page.evaluate` 同时取得就绪状态、最终 URL 和 HTML，消除检查/读取之间的节点替换竞态。仍保留可见验证码暂停、项目身份及区域核对，不放宽住宅准入。
- 新增动态节点消失和字段延迟到达测试，先 2 failed，再相关 8 文件 **127 passed**，2 条第三方弃用警告。NAS 临时浏览器同一会话顺序读取世茂栖棠誉湾 4.87 秒、领界大厦 1.80 秒；通过临时 HTTP worker 完整读取两项目，分别 5.87 秒和 8.13 秒，领界补证取得完整实际地址。
- 备份已发布的旧 worker 到 `backups/housing-browser-fix-20261027-01a17b23/browser_worker-before-snapshot.py`，旧镜像保留为 `personal-web-housing-map-browser:rollback-snapshot-fix-20261027`。仅上传/重建/更新 browser，后端未再次重启。
- 第一次正式完整复验远程命令达到 50 秒超时，未获得完整输出，不计作成功；随后单页 5.62 秒成功，正式完整复验（已保存 stdout/stderr）7.36 秒成功：主页 3.96 秒，预售证累计 7.36 秒，领界大厦为非住宅/在售，完整地址 `杭州市滨江区东信大道1188号（东信大道与江南大道交汇处）`。输出保留于 NAS `/tmp/housing-browser-fix-20261027-01a17b23/production-sequence-result.txt`。
- 只读实测未保存小区资料、未启动批量采集。临时 HTTP worker 已停止并自动删除。外站网络/人工验证仍可能导致后续任务暂缓；本次实测证明该节点竞态修复及领界完整取证可成功，不承诺剩余项目全部成功。

## 2026-10-27 缓存深链与局部失败策略发布

- 用户确认修改缓存重试与暂停策略。新增5项测试先失败，修改后加入批次级回归，相关8文件 **134 passed**，2条第三方弃用警告。覆盖首项超时后其余4项继续、3个连续超时后余下2项暂缓、普通超时后出现验证码时摘要仍为验证冷却。主程序仍保留项目名称/区域/预售证身份验证，不推断用途。
- BrowserClient 在冷浏览器上下文请求证件前访问自己的项目主页；已成功准备的主页不重复访问，worker错误后清理准备状态。cache事实及原始时间仍复用，准备页面不作为新证据发布。
- `browser_timeout` 在连续前2次仅失败本项目，异常带 `task_paused=False`；第三次锁定后续请求，任何成功页面会重置计数。验证码/服务故障立即暂停仍保留。worker的单项超时提示不再声称整轮已暂停。
- NAS 临时目录 `/tmp/housing-cache-retry-20261027-01a17b23`，临时 worker 使用实际相同配置；临时后端挂载 `housing-map-data:/snapshot:ro`，读取真实领界 previous缓存。输出 `real-cache-result.txt`：先领界主页，再预售证；9.39秒完整地址成功，下一项目9.41秒成功，总18.80秒。未调用写入接口。
- 为避免再次把NAS工作区改脏，本次基于当前运行镜像叠加修改的三个文件构建发布镜像（临时 Dockerfile.backend/browser 和 .dockerignore 仅包含指定源码）。后端基底为2be66fa...（包含其他已发布改动），保留为 `personal-web-housing-map-backend:before-cache-retry-20261027`；browser基底保留为对应同名tag。Git源码未改动。
- 新正式 backend=`sha256:236ddc942c9950c8a7b2e98b9a51fd1f59cf94416727e175d59a80e2d9718514`，browser=`sha256:76155395f2a02269099ed7277dff7a885f73eefae42b963ab66be9dfa0f32443`；另带 `cache-retry-20261027` tag。Compose按browser→backend逐个无build更新，两者healthy。
- 正式后端读取其真实已保存缓存，用正式worker：领界9.32秒取得非住宅和完整地址，下一项目累计11.24秒成功；`production-cache-result.txt`明确记录请求顺序主页→证件→下一项目。未写业务数据，未启动批量采集。临时worker随后停止自动删除。
- 本轮没有自动commit/push。NAS Git源码仍为发布前版本，后续常规源码重建前必须先合入本地修复，否则会覆盖这次发布；不能以Git工作区干净推断镜像与Git源码相同。回滚为重tag `before-cache-retry-20261027` 到对应默认镜像名并仅up两个服务，不重建、不操作业务卷。

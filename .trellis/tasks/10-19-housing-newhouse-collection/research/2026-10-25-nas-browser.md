# NAS 新房浏览器调研（2026-10-25）

## 结论

普通浏览器获取方案已通过 NAS 小样本验证：三个新房主页均无需登录、人工验证码或指纹修改，读到了项目名称、滨江区域、住宅用途、在售状态。当前后端容器没有浏览器接入，宿主机已有 Chrome；缺口是应用接入，并非 NAS 无法运行浏览器。

浏览器成功打开主页不等于能立即自动收录：三个主页及各自 basicinfo 页的实际地址均有字面省略号。春来晴翠园的预售证页面已返回完整的楼盘坐落，但该深层页面后续出现验证码遮罩，证件详情按钮的普通点击被遮挡。不得把这条证件路径报告为稳定无人值守可用，更不能推断 19 个项目均能完成自动收录。

## 环境与边界

- 时间：2026-10-25 23:32–23:39（Asia/Shanghai）。
- NAS：x86_64；约 15.4 GiB 总内存，调研前可用约 7.8 GiB；根分区可用约 124 GiB。这是宿主机快照，未测浏览器峰值资源。
- 已有 Google Chrome 155.0.8059.39，路径 `/opt/google/chrome/chrome`。
- 已有 Playwright Core 1.59.1，来自宿主机 openclaw 的依赖。仅调研复用，不建议生产应用依赖其私有安装路径。
- 临时 Node.js + Playwright 会话，无头模式、默认自动化行为、独立无登录上下文，locale=zh-CN，timezoneId=Asia/Shanghai。
- 同一批次串行复用 context，项目间隔 5 秒，单次导航 25 秒上限。未使用 stealth、代理切换、人工验证码求解或强制点击。
- 未安装软件、修改生产镜像/服务配置、触发采集任务、写生产数据库或更改名单。浏览器正常打开公开页产生的站点访问统计不在本地控制范围内。
- 全部浏览器已在 finally 中关闭；最后检查没有残留的本次浏览器进程。

## 主页面实测

| 项目 | project ID | 页面结果 | 读取耗时 | 地址结果 |
| --- | --- | --- | --- | --- |
| 春来晴翠园 | 2946115152 | 滨江 / 住宅 / 在售 | 8.446 秒 | 东至规划道路，南至零磁谷街绿化，西至浦沿路绿.. |
| 泊玺骏庐 | 3304038073 | 滨江 / 住宅 / 在售 | 5.362 秒 | 东至规划占家湖路，南至最葵园南侧支 路，西至.. |
| 月澜雅颂里 | 3277058158 | 滨江 / 住宅 / 在售 | 2.373 秒 | 东至文水河规划绿化，南至生地街，西至浦沿路绿.. |

页面来源均为 `https://www.tmsf.com/newhouse/property_33_<project ID>_infoUpgrade.htm`。首次导航记录到两次相同主页的 200 响应，随后同一会话其他项目只记录到一次。浏览器产生了站点会话/验证 Cookie（只记录名称，不保存或输出值）。这支持自动 JS 验证解释，但不作为长期可访问性保证。

把三份浏览器 HTML 通过标准输入交给线上现有 `_parse_project_detail` 做纯解析，均返回住宅/new_house/在售，以及 `address_error=新房详情地址显示不完整（截断），需补完整实际地址`，address 为空。说明现有主要字段选择器适用，浏览器接入后仍需要地址补证。没有调用任何写入函数。

三个 basicinfo 页亦已分别访问，楼盘地址仍截断。泊玺骏庐的“售楼处地址”恰好是一段完整四至，但字段语义仍是售楼处，不能自动冒充楼盘坐落。

## 完整地址来源与限制

春来晴翠园主页公开链接到：

`https://www.tmsf.com/newhouse/presell_33_2946115152_3333500499.htm`

此页预售证 202600601 的附加详情 DOM 已被正常页面脚本填充：

- `#propertynamerr`：绿城英冠春来晴翠（与项目索引营销别名一致）。
- `#projnamerr`：杭政储出【2025】8号地块商品住宅(设配套公建)项目16# 楼。
- `#locatedrr`，标签“楼盘坐落”：东至规划道路，南至零磁谷街绿化，西至浦沿路绿化，北至回龙庵街。
- `#selladdressrr`，标签“售楼部地址”：浦沿路与零磁谷街交汇处往北100米。
- `#persellnorr`：202600601。

页面脚本从公开的 `NewPropertyHz_createPresellInfo.jspx` GET 响应读取 `property.located` 并填充 `#locatedrr`。这一发现确认了完整实际地址的语义和出处；它不是售楼处或地图格式化地址。该 endpoint 只通过站点正常页面访问观察到，未实施绕过验证码的直接请求。

后续普通点击“预售证详细信息”时，Playwright 报告 `.captcha_cover` 等元素拦截点击，30 秒超时。本批次立即结束，没有继续访问其余两个预售证。现有 DOM 返回完整地址不代表该弹层已成功显示，也不证明此数据端点可以绕过人工验证长期直连。页面同时加载了逐套价格请求及验证码组件，本次没有进一步确认验证码针对价格还是地址请求，不能把它扩大解释为完整地址必然需要人工验证。

basicinfo 的“更多详细信息”链接实际跳到 `toPropertyCommList.htm` 网友评价页，不能作为地址补全入口。

## 建议实施范围（尚未实施）

1. 给新房详情接入独立浏览器 worker，名单索引和二手房保持现有 HTTP 路径。浏览器在任务开始时按需启动，任务内复用会话并串行处理，结束关闭；单项更新复用同一个获取接口。
2. 用固定版本、独立运行环境部署 worker，限定内网调用、目标站点/路径和任务超时。不要直接耦合 openclaw 的 npm 依赖或用户个人浏览器；无需为普通采集开放桌面/VNC。此次验证的是宿主机运行环境，独立容器尚需另做小样本部署验证。
3. 分开保存“详情已验证”和“完整实际地址待补”。本次可明确改善用途、区域、状态采集，但不能宣称已完成全部准入条件。
4. 详情地址截断时，有预算且无验证码才尝试主页明确链接的一个预售证。核对 URL 中 project ID、页面/响应项目别名、区域证据、预售证 ID/证号；只取实际“楼盘坐落”，保留独立 address_evidence_url、证号及采集时间。
5. 检测 JS 验证等待与人工验证码时分别处理。人工验证码出现后停止该新房详情/地址队列，保留候选和旧事实，记录可操作的暂停原因；不要为每个项目重复撞验证。
6. 稳定性验收需覆盖新会话与复用会话、3 个样本、取消/重启、地址缺失/截断、身份错配、人工结果保护和浏览器资源释放；然后才做 19 个候选的只读补录预览。正式生产补录沿用原任务的独立授权边界。

优先选择独立 worker，是为控制浏览器依赖、故障与资源生命周期。把 Playwright/Chromium 直接装进现有 FastAPI 镜像也是可行候选，但会加重主服务镜像；仅凭此次研究没有必要立即改主镜像。资源上限需在目标容器实测，不给出未经测量的固定内存保证。

## 代码接入点

- `src/services/tmsf_property_type.py`：`fetch_project_facts_by_id`、`fetch_project_facts` 共享详情获取与解析；地址补证必须维持 project/community 身份隔离。
- `src/services/directory_collection.py`：任务级浏览器复用、限速、取消、暂停分类；当前缓存成功要求用途及完整地址，后续需要避免为地址待补条目反复拉已验证详情。
- `src/services/community_enrichment.py`：单项重试使用同一新房获取能力，网络请求在写事务外，保留快照/人工保护。
- `docker-compose.nas.yml`：若采用 worker，增加独立部署与健康检查，现有主服务不必直接依赖宿主机路径。

## 调研证据

NAS 临时文件（非生产数据，临时目录可能被清理）：

- `/tmp/tmsf-newhouse-research-tOFxaY/`：三份主页 HTML 与截图。
- `/tmp/tmsf-newhouse-address-rYdcCN/`：春来晴翠园 basicinfo HTML。
- `/tmp/tmsf-newhouse-deep-PcJXAb/`：泊玺骏庐/月澜雅颂里 basicinfo、春来晴翠园评论页。
- `/tmp/tmsf-newhouse-presell-WQP74L/`：春来晴翠园预售证 DOM 与截图（完整坐落字段已加载）。
- 本地保留的 [预售证入口截图](./presell-validation.png) 展示入口页面；截图时验证码遮罩尚未显示，不作为后续弹层点击成功或验证码状态的证据。
- SSH job：`job-mvnzl4y7-39cb`（三主页成功）、`job-mvnzmh5u-8b5a`（首个 basicinfo 可读，但探针误用主页选择器提前停止，后由修正探针补齐）、`job-mvnznuu6-4108`（其余 basicinfo / 评论页）、`job-mvnzp9xk-e372`（预售证入口）、`job-mvnzrazo-2cf3`（证件弹窗点击被验证码遮罩拦截，退出 1）。

官方文档核对：

- [Playwright Docker](https://playwright.dev/python/docs/docker)：浏览器及系统依赖、独立用户与 sandbox；官方示例镜像定位测试/开发，不直接当作生产爬虫部署方案。
- [Playwright Browsers](https://playwright.dev/python/docs/browsers)：库与浏览器版本需匹配、可只安装需要的浏览器。
- [Playwright Authentication](https://playwright.dev/python/docs/auth)：会话状态可复用，包含 Cookie 的状态文件不应进入仓库。
- [Playwright BrowserType](https://playwright.dev/docs/api/class-browsertype)：支持远程浏览器连接；Playwright 协议版本匹配要求和 CDP 能力限制。
- [Chrome remote debugging changes](https://developer.chrome.com/blog/remote-debugging-port)：调试应使用独立 profile，不接管日常个人 profile。

这次仅新增调研记录，没有修改业务代码或执行生产补录。

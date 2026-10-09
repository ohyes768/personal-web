# RSS Relay 后端与网页契约

## Scope / Trigger
修改 backend/rss-relay 或 apps/rss-relay 的渠道推送、管理、订阅和对接文档时读取本文件。

## Signatures
- POST /api/post：{title,content,url?,source?,channel?}。
- GET /api/rss.xml?token=...&channel=...&limit=50；省略channel为全量。
- GET /api/channels?include_disabled=true：{channels:[{id,title,description,enabled}]}。
- POST /api/channels：{id,title,description}。
- PATCH /api/channels/{id}：{title?,description?,enabled?}。
- 对外代理前缀 /rss/api/rss-relay/；不能沿用未配置的 /rss/personal.xml 路径。

## Contracts
渠道名称去除首尾空白后非空且最多100字符，说明最多500字符；标识为小写字母数字和分段连字符，最多64字符。PATCH字段省略表示不修改，显式null拒绝。
channel为稳定内容频道，source记录推送工具，不可互相推断。缺失channel的旧文章和推送归unclassified。ID创建后不可更改，系统未分类不可停用。停用后拒绝新推送，已有feed仍返回历史文章。
渠道登记保存在data/channels.json（现有持久卷覆盖），配置仅首次种子；重建不可覆盖用户设置。采用原子替换，失败不返回成功、不更新内存。
筛选渠道必须先于排序和limit；GUID保持原文章ID。频道清单来源是登记，不是最近文章。
RSS_RELAY_TOKEN继续保护所有feed；NEXT_PUBLIC_RSS_TOKEN供现有网页订阅链接。RSS_RELAY_PUBLIC_FEED_URL可覆盖后端公开self URL；对接示例与API一致，不日志输出完整带token链接。

## Validation & Error Matrix
| 行为 | 状态 |
|---|---|
| 未知推送channel / 非法字段 | 422 |
| 重复channel ID / 已停用渠道推送 | 409 |
| 未知渠道feed或编辑目标 | 404 |
| 无效RSS token | 401 |
| 缺失必填RSS token | FastAPI请求校验422 |

## Good / Base / Bad Cases
Good：先网页创建xinwen，再推送channel=xinwen，订阅该频道仅返回新闻联播。
Base：旧推送不带channel，仍在全量和未分类订阅可读。
Bad：使用source=openclaw自动分到新闻联播；用截断后的50篇推导渠道；改名时改ID导致链接失效。

## Tests Required
断言频道隔离与先过滤后limit、RSS标题/self URL/GUID、旧文档回退、token拒绝、未知与停用频道状态、重启持久化、首次种子不覆盖、写失败不更新内存、并发变更不丢失。
网页验证直接复制、失败手动兜底、管理保存刷新、动态对接示例、手机布局及焦点恢复。

## Wrong vs Correct
Wrong：list_posts(limit=50)之后按channel筛选。
Correct：list_posts中先应用channel过滤，再排序并截取limit。
Wrong：每次启动把app.yaml种子覆盖channels.json。
Correct：只在登记文件不存在时初始化，已有文件是运行时来源。

## 构建 token 链路
前端Dockerfile的ARG/ENV和compose build.args之外，scripts/deploy-nas.sh默认buildx直构建也必须通过get_buildx_config显式传入NEXT_PUBLIC_RSS_TOKEN=${RSS_RELAY_TOKEN:-}，否则compose配置不会参与该构建。scripts/tests/test_rss_build_args.py执行真实build函数、用假docker断言构建收到共享token；测试无需真实Docker或密钥。修复后必须重建前端镜像，单纯restart不会改变已内联变量。

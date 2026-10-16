# RSS Relay 后端与网页契约

## Scope / Trigger
修改 backend/rss-relay 或 apps/rss-relay 的渠道推送、管理、订阅和对接文档时读取本文件。

## Signatures
- POST /api/post：{title,content,url?,source?,channel?}；201 返回 {id,created_at,file,detail_url}。
- GET /api/post/{id}：单篇文章，响应体字段与 /api/posts 列表项一致；未知/非法/已过期（>15天）id 均 404。无鉴权，id 即凭证（{时间戳}-{6位hex}，不可枚举）。
- GET /api/rss.xml?token=...&channel=...&limit=50；省略channel为全量。
- GET /api/posts?limit=50&channel=xinwen；省略channel为全量，未知渠道404，停用渠道历史可读。
- GET /api/channels?include_disabled=true：{channels:[{id,title,description,enabled}]}。
- POST /api/channels：{id,title,description}。
- PATCH /api/channels/{id}：{title?,description?,enabled?}。
- 对外代理前缀 /rss/api/rss-relay/；不能沿用未配置的 /rss/personal.xml 路径。

## Contracts
渠道名称去除首尾空白后非空且最多100字符，说明最多500字符；标识为小写字母数字和分段连字符，最多64字符。PATCH字段省略表示不修改，显式null拒绝。
channel为稳定内容频道，source记录推送工具，不可互相推断。缺失channel的旧文章和推送归unclassified。ID创建后不可更改，系统未分类不可停用。停用后拒绝新推送，已有feed仍返回历史文章。
渠道登记保存在data/channels.json（现有持久卷覆盖），配置仅首次种子；重建不可覆盖用户设置。采用原子替换，失败不返回成功、不更新内存。
筛选渠道必须先于排序和limit；GUID保持原文章ID。频道清单来源是登记，不是最近文章。
网页分类以channel为准，名称从渠道登记读取，不用source作为渠道名。URL保存选中渠道，清单失败时不得误判为未知并重置；快速切换的旧文章请求不得覆盖新选择。total为当前返回条数，不是历史总数。
网页“渠道”入口使用统一紧凑弹窗，复制订阅与管理共用列表；名称和说明单行截断，编辑和停用/恢复按钮直接显示，桌面位于名称行右侧，手机位于说明行右侧。编辑表单和推送示例按需展开。停用默认隐藏，显示后仍可复制历史订阅链接；系统渠道不可编辑或停用。变更成功使用API响应更新弹窗并刷新主页渠道清单，不整表加载以免丢失滚动位置。
RSS_RELAY_TOKEN继续保护所有feed；NEXT_PUBLIC_RSS_TOKEN供现有网页订阅链接。RSS_RELAY_PUBLIC_FEED_URL可覆盖后端公开self URL；对接示例与API一致，不日志输出完整带token链接。

详情页契约：detail_url 基址取 app.rss.channel.link（rstrip("/") 后拼 /view/{id}），不新增配置项，反代路径变化时只改这一处；后端不校验该 URL 可达。前端详情页路由 src/app/view/[id]/page.tsx（basePath=/rss），三态：加载骨架 / 404（"文章不存在或已过期"+保留期说明）/ 错误重试。store.find_post 的 id 校验（_validate_post_id 防路径穿越）必须先于任何文件系统访问；过期判断内置 max_age_days=15，与 list_posts 语义一致。

## Validation & Error Matrix
| 行为 | 状态 |
|---|---|
| 未知推送channel / 非法字段 | 422 |
| 未知/非法/过期 post id（单篇读取） | 404 |
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
Wrong：前端按 `e.message.includes('404')` 判断单篇不存在——后端 404 detail 是 "Post not found"，消息不含 "404"，判断永不成立。
Correct：api-client 抛带 status 的 ApiError，按 `e.status === 404` 分支。
Wrong：basePath=/rss 下原生 `<a href="/">` 当"返回列表"——原生 a 不补 basePath 前缀，实际跳驾驶舱首页。
Correct：写 `href="/rss"`（Next `<Link>` 才自动补 basePath）。
Wrong：每次启动把app.yaml种子覆盖channels.json。
Correct：只在登记文件不存在时初始化，已有文件是运行时来源。

## 构建 token 链路
前端Dockerfile的ARG/ENV和compose build.args之外，scripts/deploy-nas.sh默认buildx直构建也必须通过get_buildx_config显式传入NEXT_PUBLIC_RSS_TOKEN=${RSS_RELAY_TOKEN:-}，否则compose配置不会参与该构建。scripts/tests/test_rss_build_args.py执行真实build函数、用假docker断言构建收到共享token；测试无需真实Docker或密钥。修复后必须重建前端镜像，单纯restart不会改变已内联变量。

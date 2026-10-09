# rss-relay（RSS 中转）

一个服务接收各渠道 Markdown 推送，按渠道提供独立 RSS 2.0 订阅。网页“订阅渠道”可直接复制链接，“管理渠道”可新增、改名、修改说明、停用和恢复。

## 路由与对接

本地后端基址：`http://localhost:8095/api`。
生产 nginx 基址：`https://web.duomi77.cn:9443/rss/api/rss-relay`。
下表均为基址后的相对路径；健康检查本地为 `/health`，生产为 `/rss/api/rss-relay/health`。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/post` | 接收 Markdown 推送 |
| GET | `/rss.xml?token=…&channel=xinwen&limit=50` | 新闻联播订阅；省略 channel 返回全部 |
| GET | `/channels` | 启用渠道清单 `{channels:[{id,title,description,enabled}]}` |
| GET | `/channels?include_disabled=true` | 管理视图完整清单 |
| POST | `/channels` | 新增渠道 `{id,title,description?}`，201 返回渠道 |
| PATCH | `/channels/{id}` | 修改 `{title?,description?,enabled?}`，200 返回渠道 |
| GET | `/posts?limit=50` | 网页文章列表，包含 channel 和 source |
| DELETE | `/posts/{id}` | 删除文章，204 成功，404 不存在 |

先在网页创建渠道，再让推送工具使用对应标识：

```bash
curl -X POST 'https://web.duomi77.cn:9443/rss/api/rss-relay/post' \
  -H 'Content-Type: application/json' \
  -d '{
    "channel": "xinwen",
    "title": "今日新闻联播分析",
    "content": "# 新闻联播\n\n正文 Markdown……",
    "url": "https://example.com/original",
    "source": "openclaw"
  }'
```

- `title`、`content` 必填且非空；`url` 可选。
- `channel` 是内容渠道，例如 `xinwen`；`source` 是推送工具来源，例如 `openclaw`，两者独立。
- 省略 channel 或传 null 归系统渠道 `unclassified`（未分类）；旧文章缺少字段也归未分类，不自动猜测历史来源。
- 渠道 ID 为 1–64 个小写字母、数字或分隔用连字符（例如 `xinwen`、`bilibili-subtitle`），创建后不可修改。名称去首尾空格后 1–100 字，说明最多 500 字。
- 新增重名 ID 为 409；未知渠道推送及非法字段为 422；停用渠道推送为 409。
- PATCH 未知渠道为 404；显式 null、修改 ID、停用未分类为 422。保存失败为 503，并保留原数据。
- 不提供物理删除渠道。停用隐藏默认订阅入口并拒绝新推送，历史文章和旧订阅链接仍可读取；恢复后继续推送。

## 订阅与迁移

```text
全部：https://web.duomi77.cn:9443/rss/api/rss-relay/rss.xml?token=<RSS_RELAY_TOKEN>
新闻联播：https://web.duomi77.cn:9443/rss/api/rss-relay/rss.xml?token=<RSS_RELAY_TOKEN>&channel=xinwen
未分类：https://web.duomi77.cn:9443/rss/api/rss-relay/rss.xml?token=<RSS_RELAY_TOKEN>&channel=unclassified
```

RSS token 来自环境变量 `RSS_RELAY_TOKEN`，所有 feed 均校验；无效或服务未配置 token 返回 401，缺少参数返回 422。
鉴权通过后，未知渠道为 404。订阅链接不要公开分享。
各渠道即使没有文章也可订阅；先按渠道筛选，再排序取 limit（默认 50，最多 200），文章 GUID 保持不变。

原来无 channel 的链接继续返回全部；推送端加入 channel 后，新文章进入对应渠道。
阅读器先添加独立订阅，再取消全量订阅，避免重复。历史归属迁移需另行确认。
改名称不改变链接或文章归属；阅读器可能缓存名称或使用用户自定义名称，需要手动刷新或改名。

## 存储与部署

`data/posts/*.md` 存储 YAML front matter（id/title/url/source/channel/created_at）和正文。
`data/channels.json` 保存渠道设置；首次启动从 `config/app.yaml` 的 `app.rss.channels` 初始化新闻联播和系统未分类，文件存在后不再用种子覆盖用户设置。
渠道文件启动加载，读写加锁，同目录临时文件写入、flush/fsync 后原子替换；写失败不修改内存。当前设计为单进程，勿开多个 uvicorn workers。

主仓库 `docker-compose.nas.yml` 使用 `rss-relay-data:/app/data`，本目录 compose 使用 `./data:/app/data`，均覆盖渠道文件。重启/重建容器保留设置，删除数据卷会丢失文章与渠道。
RSS Atom self 链接使用 `app.rss.channel.self_url`，可用 `RSS_RELAY_PUBLIC_FEED_URL` 覆盖，附带 token/channel/limit，避免输出容器内部地址。反向代理路径变化时同步修改此配置与前端公开基址。
内容保留 15 天；启动及每天 03:03 清理过期文件。

RSS 读取有 token；文章及渠道管理接口沿用现有受限网络部署边界，无独立鉴权。生产 nginx 将 `/rss/api/rss-relay/*` 直接转发后端；应保证访问边界受限后使用管理接口。

## 本地开发和验证

```bash
cd backend/rss-relay
uv sync --dev
uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8095 --no-access-log
uv run pytest tests -q
```

Windows pytest 临时目录固定到当前项目 `.pytest-tmp`，不与 WSL 并发共享。

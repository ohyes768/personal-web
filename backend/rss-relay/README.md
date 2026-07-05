# rss-relay（个人 RSS 中转）

接收 agent（openclaw 等）推送的 markdown，对外提供 RSS 2.0 feed，配合 NAS freshrss 阅读。

## 工作流

```
agent 采集 → POST /api/post → 写文件 → GET /api/rss.xml → freshrss 抓取
                                       (保留 15 天，定时清理)
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/post` | 接收 markdown 推送（无鉴权，内网部署） |
| `GET` | `/api/rss.xml?token=xxx&limit=50` | RSS 2.0 feed（**token 必填**） |
| `GET` | `/health` | 健康检查 |
| `GET` | `/` | 服务信息 |

### 鉴权

RSS feed 用 query string `?token=xxx` 鉴权，token 来自 `RSS_RELAY_TOKEN` 环境变量。
未配置时所有 RSS 请求都会被 401 拒绝（避免误以为已加保护）。
校验用 `hmac.compare_digest` constant-time 比较，防时序攻击。

### 推送示例

```bash
curl -X POST http://localhost:8095/api/post \
  -H "Content-Type: application/json" \
  -d '{
    "title": "OpenAI 发布 GPT-5",
    "content": "# GPT-5\n\n正文 markdown...",
    "url": "https://example.com/...",
    "source": "openclaw"
  }'
```

字段：
- `title`（必填）
- `content`（必填，markdown）
- `url`（可选，原文链接）
- `source`（可选，来源标识）

## 本地开发

```bash
cd backend/rss-relay
python -m venv .venv
.venv\Scripts\activate         # Windows
# .venv/bin/activate            # Linux/macOS
pip install -e .
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8095
```

## 部署

主仓库 `docker-compose.nas.yml` 已加 `rss-relay-backend` service。

对外 URL（走 nginx）：
- **freshrss 订阅**：`https://<nas-host>:9443/rss/personal.xml?token=<RSS_RELAY_TOKEN>`
- **agent 推送**：`POST https://<nas-host>:9443/api/rss-relay/post`（无鉴权，依赖网络隔离）

## 文件结构

```
data/posts/
├── 20260702-143052-a1b2c3.md    # 每个 post 一个 markdown 文件
└── ...
```

文件内含 YAML front matter（id/title/url/source/created_at）+ body。

清理策略：APScheduler 每天 03:03 跑 + 启动时跑一次，删 mtime > 15 天的文件。

## 安全

- **RSS feed**：`?token=xxx` 鉴权（参考 douyin-processor 模式，`hmac.compare_digest`）
- **POST /api/post**：无鉴权（依赖 NAS 网络隔离）。如需公网部署，建议加 nginx IP 白名单或自加 token

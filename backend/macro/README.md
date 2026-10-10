# Global Macro Finance

全球宏观经济债券利率数据服务

## 功能

- 获取美债、欧债、日债利率数据
- 提供 API 接口供 n8n 和前端调用
- 支持历史数据查询
- 自动数据更新和重试机制

## API 接口

### POST /api/update
n8n 调用此接口触发数据更新

```bash
curl -X POST http://localhost:8094/api/update
```

### GET /api/data
查询历史数据

```bash
curl "http://localhost:8094/api/data?start_date=2024-01-01&end_date=2024-12-31"
```

### GET /api/health
健康检查

```bash
curl http://localhost:8094/api/health
```

## 开发

### 环境设置

```bash
cd scripts
./setup.sh
```

### 配置环境变量

编辑 `.env` 文件：

```bash
FRED_API_KEY=your_fred_api_key_here
```

### 启动服务

```bash
cd scripts
./start.sh
```

### 停止服务

```bash
cd scripts
./stop.sh
```

## Docker 部署

### 构建镜像

```bash
docker build -t macro .
```

### 运行容器

```bash
docker run -d \
  --name macro \
  -p 8094:8094 \
  -e FRED_API_KEY=your_key \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  macro
```

## 技术栈

- Python 3.12
- FastAPI
- pandas
- fredapi


## 日频图表分析助手

首期入口位于“利率利差”中的中国国债子图。点击“指标说明”可即时阅读；
“帮我分析”默认解释图中十年收益率和10Y−2Y利差，使用当前可视日期范围。
两年收益率由同日十年收益率减利差推导，DR007是独立参考。

NAS部署通过docker-compose.nas.yml注入：

- `ANALYSIS_PASSWORD`：自己设置的分析解锁密码。
- `ANALYSIS_SIGNING_SECRET`：单独生成的长随机签名密钥，例如用Python secrets.token_urlsafe(48)。
- `DEEPSEEK_API_KEY`：DeepSeek服务密钥。
- `DEEPSEEK_MODEL`：默认deepseek-flash，可按账户可用模型调整。

不要把这些值提交进Git。未配置时分析不可用，原图表和说明仍可使用。
生产保持`ANALYSIS_COOKIE_SECURE=true`并使用HTTPS；本地HTTP测试可显式设false。
修改密码或签名密钥会让旧解锁凭证失效。同浏览器解锁7天，主动“锁定分析”撤销当前凭证。
密码只保护付费分析，原有数据查询不改变。撤销列表在内存中，服务重启不保留该列表；
需要跨重启强制注销时修改密码/签名密钥。

分析聊天与快照只保存在内存：刷新网页不恢复聊天，服务重启也不恢复。
闲置30分钟或创建超过2小时过期，每会话最多10轮，全局最多2个生成请求。
同一请求ID不重复调用模型；取消或断开会停止本地上游请求，已经产生的费用无法撤销。
首次分析和追问都基于同一原始数据快照；图表范围或数值变化后主动重新分析。

新增日频图：在`src/analysis/registry.py`登记稳定chart_id、原始CSV列、单位和分析策略；
扩展通用快照统计所需的领域计算，再通过公共MacroEChart入口与共享助手接入。
不要把前向填充后的显示数组当原始观测，不要把客户端数值作为权威证据。
当前只开放中国国债图，其余日频图按任务清单后续接入。

部署时需同时更新宏观后端、前端及nginx配置。分析专用代理关闭缓冲/缓存，
保留Host端口并配置120秒读取超时；本地Next rewrite与生产nginx路径均为`/api/macro/analysis/*`。
验证用假模型通过并不等于真实DeepSeek调用验收；配置真实密钥后检查首轮、追问和错误反馈。

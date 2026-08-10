# douyin-processor 技术规范文档

## 1. 概述

### 1.1 背景
douyin-processor 是服务器端视频处理服务，负责从 file-system-go 获取已上传的视频文件，提取音频并进行 ASR（自动语音识别）处理，最终将识别结果保存到本地文件系统供查询。

### 1.2 目标
- **核心目标**：从 file-system-go 获取 WAV 音频 URL → 直接调用 ASR 识别 → 保存结果
- **附加目标**：提供 API 接口供 n8n 和前端查询处理状态和结果
- **非目标**：不负责视频采集和音频转换（由 douyin-collector 负责）

### 1.3 项目关系
```
douyin-collector (Windows 客户端)
    ↓ 采集视频 → 转换为 WAV → 上传 WAV
file-system-go (ECS 文件服务器)
    ↓ 存储 WAV，提供公网 URL
douyin-processor (Linux 服务器)
    ↓ 使用 URL 调用 ASR
n8n / 前端
    ↓ 获取识别结果
```

### 1.4 网关对接
- **personal-web/gateway**：通过 app/routers/douyin.py 路由转发
- **api-gateway**：通过 config/services.yaml 动态配置

## 2. 功能需求

### 2.1 核心功能

| 功能 | 优先级 | 描述 |
|------|--------|------|
| 音频列表获取 | P0 | 从 file-system-go 获取 WAV 音频列表 |
| URL 拼接 | P0 | 将相对路径拼接为完整公网 URL |
| ASR识别 | P0 | 直接使用 URL 调用阿里云 ASR |
| 结果保存 | P0 | 将识别结果保存到本地文件 |
| 状态管理 | P1 | 记录音频处理状态到 JSON 文件 |
| 结果查询 | P1 | 提供 API 查询处理结果 |

### 2.2 用户故事

```
n8n 工作流
    → 调用 POST /api/process
    → douyin-processor 获取 WAV 音频列表
    → 逐个处理音频
    → 拼接完整 URL（公网可访问）
    → 直接使用 URL 调用 ASR 识别
    → 保存结果到 data/output/
    → 更新状态到 data/status.json
    → 完成

前端用户
    → 调用 GET /api/videos/{id}/result
    → 获取指定音频的 ASR 识别结果
    → 展示给用户
```

## 3. 技术决策

### 3.1 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.12+ | 主要开发语言 |
| FastAPI | 最新版 | Web 框架 |
| uvicorn | 最新版 | ASGI 服务器 |
| httpx | 最新版 | HTTP 客户端（调用外部服务） |
| PyYAML | 最新版 | 配置文件解析 |
| Loguru | 最新版 | 日志管理 |
| uv | 最新版 | Python 包管理工具 |
| Docker | 最新版 | 容器化部署 |

### 3.2 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Server                          │
│                      (Port 8093)                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      API Endpoints                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  POST        │  │  GET         │  │  GET         │      │
│  │  /api/process│  │  /api/videos │  │  /health     │      │
│  └──────────────┘  │  /{id}/result│  └──────────────┘      │
│                     └──────────────┘                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Audio Processor                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  获取音频列表 │  │  拼接 URL     │  │  ASR识别     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │  保存结果     │  │  更新状态     │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              External Services                               │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │file-system-go│  │  阿里云 ASR   │                         │
│  │  (WAV存储)   │  │  (URL识别)   │                         │
│  └──────────────┘  └──────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 方案权衡记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 状态管理 | SQLite/JSON | JSON文件 | 简单直接，无需额外依赖 |
| 触发方式 | 定时/手动 | 手动触发 | 由 n8n 调用，无需定时任务 |
| 结果格式 | 文本/JSON | 完整JSON | 保留时间戳等完整信息 |
| 错误处理 | 接口返回/仅日志 | 仅日志 | 简化错误处理流程 |

## 4. 数据设计

### 4.1 数据模型

#### VideoInfo（复用）
```python
@dataclass
class VideoInfo:
    """视频信息"""
    aweme_id: str          # 视频 ID
    title: str             # 视频标题
    author: str            # 作者昵称
    video_url: str         # 视频 URL
    desc: str = ""         # 视频描述
    create_time: int = 0   # 创建时间戳
```

#### ASRResult（复用）
```python
@dataclass
class ASRResult:
    """ASR 识别结果"""
    aweme_id: str
    text: str              # 识别文本
    timestamp: List[Dict]  # 时间戳信息
    confidence: float      # 置信度
    duration: int          # 音频时长
```

#### ProcessStatus（新建）
```python
@dataclass
class ProcessStatus:
    """处理状态"""
    aweme_id: str
    status: str            # pending/processing/completed/failed
    created_at: str
    updated_at: str
    error: str = ""        # 错误信息
```

### 4.2 配置文件（config/app.yaml）

```yaml
app:
  # 服务器配置
  server:
    host: "0.0.0.0"
    port: 8093

  # file-system-go 配置
  filesystem:
    base_url: "http://file-system-go:8000"
    query_endpoint: "/api/videos/query"
    timeout: 30

  # 文件配置
  files:
    output_dir: "data/output"
    status_file: "data/status.json"

  # ASR配置
  asr:
    provider: "aliyun"
    model: "fun-asr"
    access_key: "ALIYUN_ACCESS_KEY"

  # 日志配置
  logging:
    level: "INFO"
    console: true
    file: true
    dir: "logs"
```

### 4.3 状态文件（data/status.json）

```json
{
  "last_updated": "2026-02-27T12:00:00Z",
  "videos": {
    "7123456789012345678": {
      "status": "completed",
      "created_at": "2026-02-27T10:00:00Z",
      "updated_at": "2026-02-27T10:05:00Z"
    },
    "7123456789012345679": {
      "status": "processing",
      "created_at": "2026-02-27T11:00:00Z",
      "updated_at": "2026-02-27T11:00:00Z"
    }
  }
}
```

## 5. API 接口设计

### 5.1 处理所有视频

**端点**：`POST /api/process`

**请求**：
```http
Content-Type: application/json
```
（无需参数）

**成功响应**：
```json
{
  "success": true,
  "message": "开始处理视频",
  "data": {
    "total": 10,
    "pending": 8,
    "processing": 2
  }
}
```

**错误响应**：
```json
{
  "success": false,
  "error": "无法连接到 file-system-go"
}
```

### 5.2 查询处理结果

**端点**：`GET /api/videos/{aweme_id}/result`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| aweme_id | string | 是 | 视频 ID |

**成功响应**：
```json
{
  "success": true,
  "data": {
    "aweme_id": "7123456789012345678",
    "status": "completed",
    "text": "识别的文本内容...",
    "timestamp": [
      {"begin": 0, "end": 1000, "text": "第一句话"},
      {"begin": 1000, "end": 2000, "text": "第二句话"}
    ],
    "confidence": 0.95,
    "duration": 60
  }
}
```

**未处理响应**：
```json
{
  "success": true,
  "data": {
    "aweme_id": "7123456789012345678",
    "status": "pending"
  }
}
```

### 5.3 健康检查

**端点**：`GET /health`

**响应**：
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

## 6. 非功能需求

### 6.1 性能要求
- 单视频处理时间：视视频长度而定
- 并发处理：串行处理（简化实现）

### 6.2 可靠性要求
- ASR 失败：记录日志，标记为失败状态
- file-system-go 不可达：返回错误，不启动处理
- 磁盘空间不足：记录日志，停止处理

### 6.3 可维护性
- 单文件不超过 300 行
- 完善的日志记录
- 状态文件支持手动编辑

## 7. 边缘情况与错误处理

### 7.1 异常场景

| 场景 | 处理策略 |
|------|----------|
| file-system-go 不可达 | 返回错误，不启动处理 |
| URL 为空或无效 | 标记为失败，继续处理下一个 |
| ASR 识别失败 | 标记为失败，继续处理下一个 |
| 磁盘空间不足 | 记录日志，停止处理 |

### 7.2 降级策略

| 级别 | 策略 |
|------|------|
| file-system-go 完全不可达 | 返回错误，不启动处理 |
| 部分视频处理失败 | 继续处理其他视频，记录状态 |

## 8. 实施计划

### 8.1 开发阶段

1. ✅ 需求分析和技术规范
2. 创建项目目录结构
3. 从 douying-collect 复用代码
4. 实现 FastAPI 服务器
5. 实现 API 接口
6. 实现视频处理器
7. 实现状态管理
8. 测试完整流程
9. 对接网关

### 8.2 file-system-go 改造

需要添加以下接口：

1. **POST /api/videos/query** - 查询视频列表
   ```json
   请求：{"filters": {"prefix": "audio", "suffix": ".mp4"}}
   响应：{"videos": [{"id": "xxx", "filename": "xxx.mp4", "size": 1024}]}
   ```

2. **GET /api/videos/{id}/download** - 下载视频
   ```http
   响应：视频文件流
   ```

### 8.3 网关对接

#### personal-web/gateway

修改 `app/routers/douyin.py`：
```python
@router.post("/process")
async def process_videos(request: Request):
    """触发视频处理"""
    target_url = f"{settings.DOUYIN_SERVICE_URL}/api/process"
    return await proxy_request("POST", target_url, headers=dict(request.headers))

@router.get("/videos/{video_id}/result")
async def get_video_result(request: Request, video_id: str):
    """获取处理结果"""
    target_url = f"{settings.DOUYIN_SERVICE_URL}/api/videos/{video_id}/result"
    return await proxy_request("GET", target_url, headers=dict(request.headers))
```

#### api-gateway

修改 `config/services.yaml`：
```yaml
services:
  douyin_processor:
    url: http://douyin-processor:8093
    enabled: true
    health_path: /health
    routes:
      - path: /api/douyin/process
        method: POST
        backend_path: /api/process
      - path: /api/douyin/videos/{video_id}/result
        method: GET
        backend_path: /api/videos/{video_id}/result
```

## 9. 用户访谈记录

### 9.1 关键决策点

| 决策 | 用户选择 | 理由 |
|------|----------|------|
| 数据来源 | 通过 file-system-go 中转 | 统一文件管理 |
| 处理触发 | n8n 调用 | 灵活的工作流控制 |
| 状态管理 | JSON 文件 | 简单直接 |
| 结果格式 | 完整 JSON | 保留完整信息 |
| 错误处理 | 仅日志 | 简化流程 |
| 代码复用 | 完全复用 | 提高效率 |
| 网关对接 | 对接两个网关 | 统一访问入口 |
| 日志级别 | INFO | 生产环境标准 |

## 10. 附录

### 10.1 目录结构

```
douyin-processor/
├── src/
│   ├── __init__.py
│   ├── server/
│   │   ├── __init__.py
│   │   ├── main.py         # FastAPI 服务器
│   │   └── endpoints.py    # API 接口
│   ├── processor/
│   │   ├── __init__.py
│   │   ├── asr_client.py       # ASR 客户端
│   │   ├── video_processor.py  # 音频处理器
│   │   ├── status_manager.py   # 状态管理
│   │   └── filesystem_client.py # file-system-go 客户端
│   ├── models.py           # 数据模型
│   └── utils.py            # 工具函数
├── scripts/
│   └── deploy.sh           # 部署脚本
├── config/
│   └── app.yaml            # 应用配置
├── docs/
│   ├── API接口文档.md       # API 文档
│   ├── 数据字典.md          # 数据字典
│   └── 部署指南.md          # 部署文档
├── data/
│   ├── output/             # 输出目录
│   └── status.json         # 状态文件
├── logs/                   # 日志目录
├── main.py                 # 主入口
├── pyproject.toml          # 项目配置
├── Dockerfile              # Docker 配置
├── docker-compose.yml      # Docker 编排
└── README.md
```

### 10.2 数据流

```
n8n 工作流
    │
    ├─→ POST /api/process
    │       │
    │       ├─→ file-system-go: POST /api/videos/query
    │       │   返回 WAV 音频列表
    │       │
    │       ├─→ 逐个处理音频
    │       │   │
    │       │   ├─→ 拼接完整 URL（base_url + relative_url）
    │       │   │
    │       │   ├─→ ASR 识别（传入公网 URL）
    │       │   │
    │       │   ├─→ 保存结果到 data/output/{aweme_id}.json
    │       │   │
    │       │   └─→ 更新状态到 data/status.json
    │       │
    │       └─→ 返回处理结果
    │
    └─→ GET /api/videos/{id}/result
            │
            └─→ 读取 data/output/{id}.json
                返回识别结果
```

### 10.3 相关项目

- **douyin-collector**：`F:/github/person_project/douyin-collector` - 视频采集客户端
- **douying-collect**：`F:/github/person_project/douying-collect` - 原始项目（代码复用源）
- **file-system-go**：`F:/github/person_project/file-system-go` - 文件服务器
- **personal-web/gateway**：`F:/github/person_project/personal-web/gateway` - 个人网站网关
- **api-gateway**：`F:/github/person_project/api-gateway` - 通用 API 网关

---

**文档版本**: v1.1
**创建时间**: 2026-02-27
**更新时间**: 2026-02-28
**状态**: ✅ 架构已优化，直接使用 URL 进行 ASR 识别

# douyin-processor

音频处理服务 - 从 file-system-go 获取 WAV 音频 URL，调用阿里云 ASR 进行语音识别

## 功能

- 从 file-system-go 获取 WAV 音频列表
- 直接使用服务器公网 URL 调用 ASR 识别（无需下载）
- 调用阿里云百炼平台 FunASR 进行语音识别
- 保存识别结果到本地文件系统
- 提供 API 接口供 n8n 和前端查询

## 安装

```bash
# 创建虚拟环境
uv venv .venv

# 激活虚拟环境
# Linux/Mac:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 安装依赖
uv sync
```

## 配置

### 1. 配置环境变量

复制 `.env.example` 为 `.env` 并填入实际的 API Key：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```
ALIYUN_ACCESS_KEY=your_actual_api_key_here
```

### 2. 配置 file-system-go 地址

编辑 `config/app.yaml`：

```yaml
app:
  filesystem:
    base_url: "http://your-ecs-ip:8000"
```

## 使用

```bash
# 运行
scripts/run.sh
```

## API 接口

### POST /api/process

触发视频处理。

**请求**：
```http
POST /api/process
```

**响应**：
```json
{
  "success": true,
  "message": "处理完成",
  "data": {
    "total": 10,
    "processed": 10,
    "success": 8,
    "failed": 2
  }
}
```

### GET /api/videos/{aweme_id}/result

获取视频处理结果。

**响应**：
```json
{
  "success": true,
  "data": {
    "aweme_id": "7123456789012345678",
    "status": "completed",
    "text": "识别的文本内容...",
    "segments": [...],
    "confidence": 0.95,
    "audio_duration": 60
  }
}
```

### GET /health

健康检查。

## 项目结构

```
douyin-processor/
├── src/
│   ├── server/              # FastAPI 服务器
│   │   ├── main.py          # 服务器主文件
│   │   └── endpoints.py     # API 接口
│   ├── processor/           # 音频处理模块
│   │   ├── asr_client.py         # ASR 客户端
│   │   ├── filesystem_client.py  # file-system-go 客户端
│   │   ├── status_manager.py     # 状态管理
│   │   └── video_processor.py    # 音频处理器
│   ├── models.py            # 数据模型
│   └── utils.py             # 工具函数
├── config/
│   └── app.yaml             # 应用配置
├── scripts/
│   └── run.sh               # 启动脚本
├── data/
│   ├── output/              # 输出目录（识别结果）
│   └── status.json          # 状态文件
├── logs/                    # 日志目录
├── main.py                  # 主入口
└── pyproject.toml           # 项目配置
```

## 相关项目

- [douyin-collector](../douyin-collector) - 视频采集客户端（下载 MP4 → 转换为 WAV → 上传）
- [file-system-go](../file-system-go) - 文件服务器（存储 WAV 音频）
- [personal-web/gateway](../personal-web/gateway) - 个人网站网关
- [api-gateway](../api-gateway) - 通用 API 网关

## 文档

- [技术规范文档](discuss/douyin-processor-技术规范.md)

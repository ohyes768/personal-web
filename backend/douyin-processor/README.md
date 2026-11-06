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

## 定时任务管理（v2.1）

定时任务由内建 `src/scheduler/` 包管理（参照 dividend-select/macro 模式），前端 `/douyin` 页面头部齿轮入口可视化管理。

| 任务 | cron（北京时间） | 动作 |
|------|------|------|
| `process_pending` | 每天 09:45 / 17:15 | 转写 status=pending 视频（阿里 FunASR → unread） |
| `cleanup_old_records` | 每天 03:07 | 删除超过保留期的 wav 源文件与 status/output 记录 |

- **管理 API**（`src/scheduler/routes.py`）：`GET /api/scheduler/jobs` · `PATCH /api/scheduler/jobs/{id}`（启停）· `POST /api/scheduler/jobs/{id}/run`（立即执行）· `GET /api/scheduler/jobs/{id}/runs?limit=20`（历史）
- **配置分工**：cron 在 `config/app.yaml`（host 只读挂载，改后 `docker restart douyin-backend`）；启停状态在 `data/scheduler/enabled.json`（douyin-data 卷，容器 recreate 不丢）；执行历史在 `data/scheduler/history.jsonl`（5MB 滚动归档，保留 3 份）
- **互斥**：cron 触发、页面立即执行、旧 `POST /api/process/pending` 共用同一把 `_process_lock`（`src/scheduler/jobs.py`），并发时后到者记 `skipped/process_busy`
- **UI 边界**：cron 不进 UI（沿 dividend 先例「cron 由配置文件固定」），只开放启停 / 立即执行 / 看历史
- 生命周期契约（shutdown drain / 单 worker / 时区陷阱）见 `.trellis/spec/backend/dividend-select/backend/scheduler-lifecycle.md`，douyin manager 同构遵循

## 项目结构

```
douyin-processor/
├── src/
│   ├── server/              # FastAPI 服务器
│   │   ├── main.py          # 服务器主文件
│   │   └── endpoints.py     # API 接口
│   ├── scheduler/           # 内建调度管理（启停/立即执行/历史）
│   │   ├── manager.py       # SchedulerManager
│   │   ├── routes.py        # /api/scheduler/* 管理 API
│   │   ├── jobs.py          # JOB_SPECS + 进程内 target + _process_lock
│   │   ├── history.py       # JSONL 执行历史
│   │   └── cron_human.py    # cron → 中文可读
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
├── tests/                   # pytest（scheduler 套件）
├── data/
│   ├── output/              # 输出目录（识别结果）
│   ├── status.json          # 状态文件
│   └── scheduler/           # enabled.json + history.jsonl（调度状态与历史）
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

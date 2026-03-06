# Start 脚本当前实现逻辑

## 概述

`start-macro-dev.bat` 用于启动 global-macro-fin 开发环境的所有服务。

---

## 职责划分

| 脚本 | 职责 | 缓存清理 |
|------|------|----------|
| **start-macro-dev.bat** | 启动服务、环境准备 | ✅ 启动前清理（确保使用最新代码） |
| **stop-macro-dev.bat** | 停止服务、关闭窗口 | ❌ 不负责 |

**设计理念**: 缓存清理应该在启动时进行，确保每次启动都使用最新代码。

---

## 执行流程

```
┌─────────────────────────────────────────────────────────────┐
│              start-macro-dev.bat (主脚本)                    │
├─────────────────────────────────────────────────────────────┤
│  1. [1/2] 启动 global-macro-fin (后端)                       │
│     ├── 切换到 backend/global-macro-fin 目录                  │
│     ├── 清理 Python __pycache__                              │
│     │   └── 删除 src/**/__pycache__                          │
│     ├── 检查虚拟环境 (.venv)                                  │
│     │   └── 不存在则创建并安装依赖                            │
│     └── 启动服务 (新窗口)                                     │
│         └── 窗口标题: "macro-fin"                             │
│         └── 命令: uvicorn src.main:app --reload --port 8094  │
├─────────────────────────────────────────────────────────────┤
│  2. 等待 2 秒                                                │
│     └── 确保后端服务启动完成                                  │
├─────────────────────────────────────────────────────────────┤
│  3. [2/2] 启动 Frontend (前端)                                │
│     ├── 切换到 frontend 目录                                  │
│     ├── 检查 node_modules                                    │
│     │   └── 不存在则 npm install                             │
│     └── 启动服务 (新窗口)                                     │
│         └── 窗口标题: "Frontend"                              │
│         └── 命令: npm run dev (Next.js)                      │
├─────────────────────────────────────────────────────────────┤
│  4. 显示服务地址                                             │
│     ├── Frontend: http://localhost:3000                     │
│     └── Macro-Fin: http://localhost:8094                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 各模块详解

### 1. 主脚本: start-macro-dev.bat

**功能**: 启动开发环境所有服务

**关键技术**:
- `setlocal enabledelayedexpansion` - 延迟变量展开
- `%~dp0` - 获取脚本所在目录
- `start` 命令 - 在新窗口启动服务
- `/k` 参数 - 保持窗口打开（便于查看日志）

**缓存清理逻辑**:
```batch
REM Clear Python cache to ensure fresh code load
echo Cleaning Python cache...
if exist "src\__pycache__" rmdir /s /q "src\__pycache__" 2>nul
if exist "src\api\__pycache__" rmdir /s /q "src\api\__pycache__" 2>nul
if exist "src\services\__pycache__" rmdir /s /q "src\services\__pycache__" 2>nul
if exist "src\utils\__pycache__" rmdir /s /q "src\utils\__pycache__" 2>nul
echo Cache cleared.
```

**虚拟环境检查**:
```batch
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
)
```

**服务启动**:
```batch
REM 后端服务
start "macro-fin" cmd /k ".venv\Scripts\activate && python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8094"

REM 前端服务
start "Frontend" cmd /k "npm run dev"
```

---

## 界面输出示例

```
========================================
  Starting Macro Dev Environment
========================================

[1/2] Starting global-macro-fin (port 8094)...
Cleaning Python cache...
Cache cleared.

[2/2] Starting Frontend (port 3000)...

========================================
  Macro Dev Environment Started
========================================

Frontend:   http://localhost:3000
Macro-Fin:  http://localhost:8094

Press any key to continue . . .
```

---

## 服务端口映射

| 服务 | 端口 | 窗口标题 | 启动命令 |
|------|------|----------|----------|
| global-macro-fin | 8094 | macro-fin | `python -m uvicorn src.main:app --reload` |
| Frontend | 3000 | Frontend | `npm run dev` |

---

## 启动参数说明

### 后端服务 (global-macro-fin)

| 参数 | 说明 |
|------|------|
| `--reload` | 代码变更自动重载 |
| `--host 0.0.0.0` | 监听所有网络接口 |
| `--port 8094` | 指定端口 8094 |

### 前端服务 (Frontend)

| 参数 | 说明 |
|------|------|
| `npm run dev` | Next.js 开发模式 |
| 默认端口 | 3000 |

---

## 设计特点

### 1. 自动环境准备

| 检查项 | 缺失时操作 |
|--------|-----------|
| 虚拟环境 `.venv` | 自动创建并安装依赖 |
| 依赖 `node_modules` | 自动 npm install |
| Python 缓存 | 每次启动前清理 |

### 2. 独立窗口

每个服务在独立的 cmd 窗口中运行：
- 便于查看服务日志
- 便于单独停止某个服务
- 窗口标题清晰标识服务类型

### 3. 缓存清理策略

**为什么在启动时清理缓存**：
- ✅ 确保每次启动使用最新代码
- ✅ 避免缓存导致的问题（如旧代码残留）
- ⚠️ 首次启动略慢（可接受）

---

## 文件结构

```
scripts/
├── start-macro-dev.bat     # 主脚本 (macro-fin 场景)
├── start-douyin-dev.bat    # 主脚本 (douyin 场景)
├── stop-macro-dev.bat      # 停止脚本
└── stop-douyin-dev.bat     # 停止脚本
```

---

## 配合使用

### 完整开发流程

```
1. 启动开发环境
   └─ start-macro-dev.bat
      ├── 清理缓存
      ├── 启动后端 (8094)
      └── 启动前端 (3000)

2. 开发/调试

3. 停止开发环境
   └─ stop-macro-dev.bat
      ├── 停止服务
      ├── 清理孤儿进程
      └── 关闭窗口
```

---

## 待优化项

1. **start-douyin-dev.bat** 需要添加相同的缓存清理逻辑
2. 可以添加服务健康检查，确认服务真正启动成功

---

*最后更新: 2026-03-06*

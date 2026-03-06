# Stop 脚本当前实现逻辑

## 概述

`stop-macro-dev.bat` 用于停止 global-macro-fin 开发环境的所有服务和窗口。

---

## 职责划分

| 脚本 | 职责 | 缓存清理 |
|------|------|----------|
| **stop-macro-dev.bat** | 停止服务、关闭窗口 | ❌ 不负责 |
| **start-macro-dev.bat** | 启动服务、环境准备 | ✅ 启动前清理（确保使用最新代码） |

**设计理念**: 缓存清理应该在启动时进行，确保每次启动都使用最新代码。

---

## 执行流程

```
┌─────────────────────────────────────────────────────────────┐
│              stop-macro-dev.bat (主脚本)                      │
├─────────────────────────────────────────────────────────────┤
│  1. [1/2] 按端口停止服务                                       │
│     ├── 扫描端口 8094 (global-macro-fin)                      │
│     │   └── taskkill /F /T /PID xxx (终止进程树)               │
│     └── 扫描端口 3000 (Frontend)                              │
│         └── taskkill /F /T /PID xxx (终止进程树)               │
├─────────────────────────────────────────────────────────────┤
│  2. [2/2] 清理孤儿子进程                                       │
│     └── stop-orphan-python.ps1                               │
│         ├── 获取所有 Python 进程                               │
│         ├── 检查命令行是否包含项目路径 (避免误杀)                 │
│         ├── 检测本地回环连接 + 不监听端口 (真正孤儿)              │
│         └── 终止孤儿子进程                                      │
├─────────────────────────────────────────────────────────────┤
│  3. 关闭服务窗口 (最后一步)                                     │
│     └── stop-windows.ps1                                      │
│         ├── 获取所有 cmd 进程                                  │
│         ├── 匹配命令行 (*8094* 或 *npm run dev*)              │
│         └── 终止匹配的 cmd 窗口                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 各模块详解

### 1. 主脚本: stop-macro-dev.bat

**功能**: 协调各模块执行

**关键技术**:
- `setlocal enabledelayedexpansion` - 延迟变量展开
- `!PID!` - 在循环中正确展开变量
- `%~dp0` - 获取脚本所在目录

**端口停止逻辑**:
```batch
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8094 " ^| find "LISTENING"') do (
    set "PID=%%a"
    taskkill /F /T /PID !PID!   # /T = 终止进程树
)
```

---

### 2. 孤儿进程清理: stop-orphan-python.ps1

**功能**: 清理主进程终止后残留的子进程（仅限项目内）

**安全改进 - 避免误杀**:
```powershell
# 获取项目根目录
$projectRoot = Resolve-Path "$PSScriptRoot\.."

# 只处理属于项目的 Python 进程
if ($cmdLine -like "*$projectRoot*") {
    # 进一步检查是否为孤儿...
}
```

**孤儿进程识别标准**:
```powershell
# 双重检查机制
$localLoopback = $conns | Where-Object {
    $_.RemoteAddress -eq "127.0.0.1" -and $_.State -eq "Established"
}

$listening = $conns | Where-Object { $_.State -eq "Listen" }

# 只有有本地回环但 NOT 监听端口才是真正的孤儿
if ($localLoopback -and -not $listening) {
    Stop-Process -Id $proc.Id -Force
}
```

**原理**:
1. **项目路径过滤**: 只处理命令行包含项目路径的进程，避免误杀其他项目
2. **双重判定**: 有本地回环连接 **且** 不监听端口 = 真正的孤儿进程
3. **正常服务**: 监听端口的进程不是孤儿，跳过

---

### 3. 窗口关闭: stop-windows.ps1

**功能**: 关闭启动时打开的 cmd 窗口

**关键修复**: 使用 `$procId` 而非 `$pid`（避免与 PowerShell 自动变量冲突）

**匹配逻辑**:
```powershell
$cmdProcesses = Get-WmiObject Win32_Process | Where-Object { $_.Name -eq "cmd.exe" }

foreach ($proc in $cmdProcesses) {
    $cmdLine = $proc.CommandLine
    $has8094 = $cmdLine -like '*8094*'
    $hasNpmDev = $cmdLine -like '*npm run dev*'

    if ($has8094 -or $hasNpmDev) {
        Stop-Process -Id $procId -Force
    }
}
```

**匹配模式**:
| 服务 | 命令行匹配模式 |
|------|---------------|
| macro-fin | `*8094*` |
| Frontend | `*npm run dev*` |

---

## 界面输出示例

```
========================================
  Stopping Dev Environment
========================================

[1/2] Stopping services by port with process tree...
Stopping service on port 8094 - PID 12345 with process tree...
Stopping service on port 3000 - PID 67890 with process tree...

[2/2] Cleaning orphaned Python processes...
Project root: F:\github\person_project\personal-web
Found 3 Python processes
Killing orphaned Python PID: 54321
Cleaned 1 orphaned Python processes (checked 2 project process)

Closing service windows...
Searching for service windows...
Found 10 cmd processes, checking each one...
MATCHED PID 48152 (8094:True, npm:False) - Closing...
  -> Successfully closed PID 48152
Closed 2 service window(s)

All services stopped.
```

---

## 关键修复历史

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 子进程残留 | `Stop-Process` 只终止单层 | 改用 `taskkill /T` |
| 变量不展开 | `%PID%` 在循环中失效 | 延迟展开 `!PID!` |
| 窗口未关闭 | `$pid` 与 PowerShell 自动变量冲突 | 改名 `$procId` |
| 误杀其他项目 | 只检查网络连接，过于暴力 | 添加项目路径检查 |
| 正常服务被杀 | 只检查本地回环，未排除监听进程 | 双重判定：回环 + 不监听 |

---

## 文件结构

```
scripts/
├── stop-macro-dev.bat      # 主脚本 (macro-fin 场景)
├── stop-douyin-dev.bat     # 主脚本 (douyin 场景) - 待更新
├── stop-orphan-python.ps1  # 孤儿进程清理（带项目路径检查）
└── stop-windows.ps1        # 窗口关闭
```

---

## 待优化项

1. **stop-douyin-dev.bat** 需要更新为相同架构
2. 窗口匹配可以更精确（当前依赖命令行字符串）

---

*最后更新: 2026-03-06*

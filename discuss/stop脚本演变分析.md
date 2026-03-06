# Stop 脚本演变分析

## 概述

本文档记录了 `personal-web` 项目中停止服务脚本的演变历史，包括设计思路、技术方案和存在的问题。

---

## 时间线

| 提交 | 日期 | 变更内容 |
|------|------|----------|
| **初始版本** | - | `stop-all-dev.bat` 统一停止所有服务 |
| **1c9b098** | 2026-03-02 | 拆分为 `stop-douyin-dev.bat` 和 `stop-macro-dev.bat` |
| **d347844** | 2026-03-02 | 新增 `stop-services.ps1` 修复窗口关闭问题 |
| **当前版本** | 2026-03-06 | 新增 `stop-orphan-python.ps1` 和 `stop-windows.ps1` |

---

## 演变过程

### 第一阶段：统一停止脚本 (初始版本)

**文件**: `scripts/stop-all-dev.bat`

```batch
@echo off
REM Stop Gateway, Frontend, douyin-processor

powershell -NoProfile -Command ^
  "$ports = @(8070, 8093, 3000);" ^
  "$names = @{8070='Gateway'; 8093='douyin-processor'; 3000='Frontend'};" ^
  "foreach ($port in $ports) {" ^
  "  try {" ^
  "    $pid = (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1).OwningProcess;" ^
  "    if ($pid) {" ^
  "      Write-Host \"Stopping $($names[$port]) (PID $pid)...\";" ^
  "      Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue;" ^
  "    }" ^
  "  } catch {}" ^
  "}"
```

**设计思路**:
- 按端口查找监听进程 (8070/Gateway, 8093/douyin-processor, 3000/Frontend)
- 使用 PowerShell 的 `Get-NetTCPConnection` 获取 PID
- 使用 `Stop-Process` 终止进程

**存在的问题**:
1. ❌ 只停止监听端口的主进程，子进程变成孤儿
2. ❌ 不关闭启动时打开的 cmd 窗口
3. ❌ 没有日志记录

---

### 第二阶段：按服务拆分 (1c9b098)

**变更**: 拆分为两个独立脚本

| 文件 | 停止的服务 | 端口 |
|------|-----------|------|
| `stop-douyin-dev.bat` | Gateway, douyin-processor, Frontend | 8070, 8093, 3000 |
| `stop-macro-dev.bat` | Gateway, global-macro-fin, Frontend | 8070, 8094, 3000 |

**设计思路**: 按业务场景拆分，用户可以选择停止哪一组服务。

**存在的问题**:
1. ❌ 仍然存在子进程孤儿问题
2. ❌ 窗口未关闭
3. ❌ 没有日志

---

### 第三阶段：窗口关闭修复 (d347844)

**新增文件**: `scripts/stop-services.ps1`

```powershell
# Find cmd processes and close them with their child processes
$cmdProcesses = Get-WmiObject Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' }

foreach ($proc in $cmdProcesses) {
    $cmdLine = $proc.CommandLine
    $procId = $proc.ProcessId

    # Match using -like (wildcard search)
    if ($cmdLine -like '*8094*' -or $cmdLine -like '*8070*' -or $cmdLine -like '*npm run dev*') {
        Write-Host "Stopping: PID $procId"

        # Stop process tree (parent + all children)
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue

        # Also kill any child processes directly
        $children = Get-WmiObject Win32_Process | Where-Object { $_.ParentProcessId -eq $procId }
        foreach ($child in $children) {
            Write-Host "  -> Child PID: $($child.ProcessId)"
            Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}
```

**改进点**:
1. ✅ 通过命令行参数匹配 cmd 窗口
2. ✅ 递归关闭一层子进程
3. ✅ 批处理脚本中增加了端口兜底清理

**仍存在的问题**:
1. ❌ 只递归一层子进程，孙进程无法处理
2. ❌ 没有日志记录
3. ⚠️ 匹配逻辑依赖于命令行字符串

---

### 第四阶段：完整解决方案 (当前版本)

**新增文件**:
- `scripts/stop-orphan-python.ps1` - 孤儿 Python 进程清理
- `scripts/stop-windows.ps1` - 服务窗口关闭

**改进内容**:

#### 1. stop-macro-dev.bat 结构优化

```
[1/3] 按端口停止服务 (使用 taskkill /T 终止进程树)
[2/3] 清理孤儿子进程 (检测本地回环连接)
[3/3] 清理 Python 缓存
[最后] 关闭服务窗口 (通过命令行模式匹配)
```

#### 2. stop-orphan-python.ps1

```powershell
# 检测孤儿子进程的标准:
$localLoopback = $conns | Where-Object {
    $_.RemoteAddress -eq "127.0.0.1" -and $_.State -eq "Established"
}
```

**孤儿进程识别逻辑**:
- 获取所有 Python 进程
- 检查网络连接
- 如果存在 `127.0.0.1` 的 `ESTABLISHED` 连接 → 判定为孤儿子进程

#### 3. stop-windows.ps1

```powershell
$patternsMap = @{
    "macro-fin" = @("python.*8094", "uvicorn.*8094")
    "Frontend"  = @("npm.*dev", "next.*dev")
}
```

通过命令行正则匹配找到对应的 cmd 进程并关闭。

#### 4. 日志功能

日志保存到 `logs/stop-macro-dev.log`，记录：
- 时间戳
- 每一步操作
- 发现的进程信息
- 操作结果

---

## 技术方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| **按端口停止** | 简单直接 | 无法处理孤儿子进程 |
| **Stop-Process** | 标准 PowerShell 方法 | 只能终止单层进程 |
| **taskkill /T** | 内置进程树终止 | 需要有监听端口的主进程 |
| **命令行匹配** | 可找到启动窗口 | 依赖命令行格式 |
| **孤儿检测** | 彻底清理残留 | 依赖网络连接特征 |

---

## 当前架构

```
scripts/
├── stop-macro-dev.bat      # 主脚本 (macro-fin 场景)
├── stop-douyin-dev.bat     # 主脚本 (douyin 场景)
├── stop-services.ps1       # 通用停止逻辑 (已废弃)
├── stop-orphan-python.ps1  # 孤儿进程清理
└── stop-windows.ps1        # 窗口关闭
```

---

## 遗留问题

### 1. 窗口关闭仍未完全解决

**现象**: `stop-windows.ps1` 中的命令行模式匹配可能无法匹配所有情况。

**原因**:
- PowerShell 的 `Get-WmiObject Win32_Process` 可能获取不到某些 cmd 进程
- 命令行格式可能因环境不同而有变化

**待解决**: 需要先调试输出实际的命令行，再调整匹配模式。

### 2. stop-douyin-dev.bat 未更新

当前只有 `stop-macro-dev.bat` 使用了新架构，`stop-douyin-dev.bat` 仍使用旧逻辑。

---

## 参考资料

- Git 提交记录:
  - `9f64849` - 德债日债图表支持
  - `d347844` - 修复停止脚本窗口关闭问题
  - `1c9b098` - 添加 global-macro-fin 子模块

- 相关文件:
  - `scripts/start-macro-dev.bat` - 启动脚本，用于查看窗口启动方式
  - `scripts/start-douyin-dev.bat` - 启动脚本

---

*最后更新: 2026-03-06*

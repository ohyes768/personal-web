# 桌面预览启动器（launch.json）的坑

> **Purpose**: `.claude/launch.json` 的 `skill-manager-api` 等配置在桌面 App
> preview_start 下反复"环境变量丢失/命令找不到"的根因与写法约束。改任何
> preview 启动命令前先读。

## 症状与根因（2026-09 实锤）

- `bash -c 'export VAR=... && python ...'` 形式：uv 报 command not found、
  或进程起来了但 pydantic Settings 报"6 个字段全 missing"。
- `cmd /c "... && set \"VAR=value with space\" && python -c \"import os; ...\""`
  形式：内层引号在 `-c "import` 处被拆断（python 报 unterminated string
  literal），`set` 根本没执行。

根因：preview 启动器把 `runtimeArgs` 拼回命令行时会**二次拆分含空格的引号
参数**，且其 shell 环境与开发终端（Git Bash）不同——`export` 的变量传不到
Windows 子进程，内层成对引号会被破坏配对。

## 写法约束（勿回退）

1. **整条 runtimeArgs 字符串里不允许出现任何双引号**——所有值（路径、密码）
   必须不含空格；`set VAR=value` 不加引号在 cmd 里同样正确（带空格才需要
   引号，而空格是禁用的）。
2. **不依赖 shell export/env 传变量**：用 `cmd /c` 的 `set` 链（cmd 自身
   set 一定传给 Windows 子进程），或直接用**仓库内 venv 的绝对相对路径**
   （`cd backend/skill-manager && .venv\Scripts\python.exe -m uvicorn ...`），
   不依赖 PATH 里有 uv/python。
3. `&&` 前后不留空格（`set X=Y&& set Z=W`），避免 cmd 把尾空格吃进变量值。
4. 参考 [`skill-manager-api` 配置](../../../.claude/launch.json)（仓库根
   `.claude/launch.json`）。

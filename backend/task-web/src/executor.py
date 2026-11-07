"""
执行器：subprocess 进程组执行、超时 kill、互斥、日志采集。

设计要点（design.md）：
- start_new_session=True + os.killpg：超时杀整个进程组，不留子进程
- stdout/stderr 追加写日志文件，DB 只存路径
- 互斥在 start_run 层做：存在 waiting/running 记录时记 skipped(reason=mutex)
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
from pathlib import Path

from . import db, profiles
from .config import get_log_dir, get_workspace_root

logger = logging.getLogger("task-web.executor")


def _get_docker_client():
    import docker

    return docker.from_env()


def resolve_cwd(cwd: str) -> str | None:
    """登记的 cwd 相对路径基于 workspace root 解析；绝对路径原样使用。"""
    if not cwd:
        return None
    p = Path(cwd)
    if p.is_absolute():
        return str(p)
    root = get_workspace_root()
    if root is None:
        return None  # 未配置 workspace 时相对目录不可用，执行会报错并留记录
    return str(root / p)


def _open_log(run_id: str, ext: str) -> tuple[Path, "object"]:
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{run_id}.{ext}"
    fh = open(path, "ab")
    return path, fh


def _kill_process_group(proc: subprocess.Popen) -> None:
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except ProcessLookupError:
            return
    # Windows 开发环境兜底：无进程组语义
    proc.kill()


def parse_env_file(path: str | None) -> dict[str, str]:
    """读 KEY=VALUE 环境文件；忽略注释与空行。值不写日志。"""
    if not path or not Path(path).exists():
        return {}
    result: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _profile_override(task: dict) -> str | None:
    """页面设置的 profile 覆盖值（纯函数式调用时 task 可能没有 id）。"""
    task_id = task.get("id")
    return db.get_profile_override(task_id) if task_id else None


def _task_env(task: dict) -> dict[str, str]:
    """合并顺序：env_file → 生效 profile 的凭证 env_file → yaml 显式 env → 强制 HERMES_PROFILE。

    profile 的凭证文件排在登记 env_file 之后（切换 profile 时网关地址/API key 以 profile
    为准），yaml 显式 env 再覆盖其余变量；`HERMES_PROFILE` 最后强制写入，避免 yaml 里
    为防漂移写死的旧值压过页面新选的 profile。
    """
    env: dict[str, str] = {}
    env.update(parse_env_file(task.get("env_file")))
    profile = profiles.effective_profile(task, _profile_override(task))
    cat = profiles.catalog() if profile else {}
    cfg = cat.get(profile) or {}
    if cfg.get("env_file"):
        env.update(parse_env_file(cfg["env_file"]))
    raw = task.get("env")
    if raw:
        try:
            env.update(json.loads(raw))
        except (ValueError, TypeError):
            logger.warning("run env 字段非法（已忽略）")
    if profile:
        env[profiles.PROFILE_ENV_KEY] = profile
    # 登记的 prompt 直接注入：触发脚本优先用 HERMES_PROMPT，jobs.json 只是回退
    if task.get("prompt"):
        env["HERMES_PROMPT"] = task["prompt"]
    return env


def _task_volumes(task: dict) -> dict[str, dict[str, str]]:
    """volumes: '宿主:容器[:rw|ro]' 列表 -> docker-py volumes 字典。

    AI 任务的 jobs.json 挂载按生效 profile 换宿主源（容器路径不变），
    否则切换 profile 后 job id 与 jobs.json 不同源，触发会查不到 job。
    """
    raw = task.get("volumes")
    if not raw:
        return {}
    specs = json.loads(raw) if isinstance(raw, str) else raw
    profile = profiles.effective_profile(task, _profile_override(task))
    result: dict[str, dict[str, str]] = {}
    for item in profiles.apply_jobs_mount(list(specs or []), profile):
        parts = str(item).split(":")
        if len(parts) not in (2, 3) or not parts[0] or not parts[1]:
            raise ValueError(f"volumes 条目非法: {item!r}")
        mode = parts[2] if len(parts) == 3 else "rw"
        if mode not in ("rw", "ro"):
            raise ValueError(f"volumes 挂载模式只支持 rw/ro: {item!r}")
        result[parts[0]] = {"bind": parts[1], "mode": mode}
    return result


def execute_docker_run(run_id: str, task: dict, timeout_seconds: int) -> str:
    """docker 引擎：一次性容器执行（方案 B）。状态语义与 shell 引擎一致。
    超时用看门狗线程杀容器（logs 流会阻塞到容器退出，无法用 wait(timeout) 实现）。"""
    image = task.get("image")
    if not image:
        raise ValueError("engine=docker 需要 image 字段")
    out_path, out_fh = _open_log(run_id, "out")
    err_path, err_fh = _open_log(run_id, "err")
    started = db.now_str()
    container = None
    timed_out = threading.Event()
    status, exit_code = "failed", None
    try:
        db.update_run(run_id, started_at=started, status="running")
        client = _get_docker_client()
        workdir = task.get("cwd") or None  # docker 引擎：cwd=容器内 working_dir
        container = client.containers.run(
            image,
            task["command"],
            detach=True,
            environment=_task_env(task),
            working_dir=workdir,
            volumes=_task_volumes(task),
            network=task.get("network") or None,
            user=task.get("run_user") or None,
            stdout=True,
            stderr=True,
        )

        def _watchdog() -> None:
            if timed_out.wait(timeout_seconds):
                return  # 主流程已正常结束
            err_fh.write(f"\n[task-web] 容器超时（>{timeout_seconds}s），强制终止\n".encode())
            err_fh.flush()
            try:
                container.kill()
            except Exception:
                pass
            timed_out.set()  # 标记超时终态（主流程 logs/wait 结束后据此判 timeout）

        watchdog = threading.Thread(target=_watchdog, daemon=True)
        watchdog.start()
        # 注意：demux 只在 attach() 上支持（logs() 无此参数，docker 7.2 实测）
        for stdout_chunk, stderr_chunk in container.attach(
            logs=True, stream=True, demux=True
        ):
            if stdout_chunk:
                out_fh.write(stdout_chunk)
                out_fh.flush()
            if stderr_chunk:
                err_fh.write(stderr_chunk)
                err_fh.flush()
        result = container.wait(timeout=60)
        exit_code = int(result.get("StatusCode", -1))
        if timed_out.is_set():
            status = "timeout"
        else:
            status = "success" if exit_code == 0 else "failed"
    except Exception as e:
        status = "failed"
        import traceback

        tb = traceback.format_exc()
        err_fh.write(f"\n[task-web] 容器执行异常: {type(e).__name__}: {e}\n".encode())
        err_fh.write(tb.encode())
        logger.error("run %s docker 异常: %s: %s", run_id, type(e).__name__, e)
        if container is not None:
            try:
                result = container.wait(timeout=30)
                exit_code = int(result.get("StatusCode", -1))
            except Exception:
                exit_code = None
    finally:
        timed_out.set()  # 停掉看门狗
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
        out_fh.close()
        err_fh.close()

    finished = db.now_str()
    db.update_run(run_id, finished_at=finished, duration_ms=_diff_ms(started, finished),
                  status=status, exit_code=exit_code)
    logger.info("run %s 结束: %s exit=%s", run_id, status, exit_code)
    return status


def execute_run(run_id: str, command: str, cwd_resolved: str | None,
                timeout_seconds: int) -> str:
    """同步执行一个 run（调用方负责在线程池里调用）。返回终态 status。"""
    out_path, out_fh = _open_log(run_id, "out")
    err_path, err_fh = _open_log(run_id, "err")
    started = db.now_str()
    try:
        db.update_run(run_id, started_at=started, status="running")
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd_resolved,
            stdout=out_fh,
            stderr=err_fh,
            start_new_session=(os.name == "posix"),
        )
    except Exception as e:  # 启动失败也要留完整记录
        err_fh.write(f"\n[task-web] 进程启动失败: {e}\n".encode())
        db.update_run(run_id, finished_at=db.now_str(), status="failed", exit_code=None)
        logger.error("run %s 启动失败: %s", run_id, e)
        return "failed"
    finally:
        out_fh.flush()
        err_fh.flush()

    status, exit_code = "running", None
    try:
        exit_code = proc.wait(timeout=timeout_seconds)
        status = "success" if exit_code == 0 else "failed"
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        try:
            exit_code = proc.wait(timeout=10)
        except Exception:
            exit_code = None
        status = "timeout"
    except Exception as e:
        logger.error("run %s 等待异常: %s", run_id, e)
        _kill_process_group(proc)
        status = "failed"
    finally:
        out_fh.close()
        err_fh.close()

    finished = db.now_str()
    duration_ms = _diff_ms(started, finished)
    db.update_run(run_id, finished_at=finished, duration_ms=duration_ms,
                  status=status, exit_code=exit_code)
    logger.info("run %s 结束: %s exit=%s", run_id, status, exit_code)
    return status


def _diff_ms(started: str, finished: str) -> int | None:
    try:
        from datetime import datetime

        fmt = "%Y-%m-%dT%H:%M:%S"
        d = datetime.strptime(finished, fmt) - datetime.strptime(started, fmt)
        return int(d.total_seconds() * 1000)
    except Exception:
        return None


def start_run(task: dict, trigger: str, scheduled_at: str | None = None) -> str:
    """创建 run 记录并后台执行。互斥：已有活跃 run 时记 skipped。
    返回 run_id（skipped 时也返回新记录的 run_id）。"""
    active = db.active_run_of_task(task["id"])
    if active:
        run_id = db.new_run_id(task["id"])
        db.insert_run({
            "run_id": run_id, "task_id": task["id"],
            "scheduled_at": scheduled_at, "started_at": db.now_str(),
            "finished_at": db.now_str(), "duration_ms": None,
            "trigger": trigger, "status": "skipped", "exit_code": None,
            "log_path": None, "missed_schedule_at": None,
        })
        # skipped 原因写日志文件，页面可直接看
        _, fh = _open_log(run_id, "err")
        fh.write(f"[task-web] 互斥跳过：已有活跃运行 {active['run_id']} (status={active['status']})\n".encode())
        fh.close()
        return run_id

    run_id = db.new_run_id(task["id"])
    timeout = task.get("timeout_seconds") or task.get("default_timeout") or 600
    db.insert_run({
        "run_id": run_id, "task_id": task["id"],
        "scheduled_at": scheduled_at, "started_at": None,
        "finished_at": None, "duration_ms": None,
        "trigger": trigger, "status": "waiting", "exit_code": None,
        "log_path": str(get_log_dir() / f"{run_id}.out"), "missed_schedule_at": None,
    })
    cwd_resolved = resolve_cwd(task.get("cwd", ""))
    if task.get("engine", "shell") == "docker":
        target, args = execute_docker_run, (run_id, task, int(timeout))
    else:
        target, args = execute_run, (run_id, task["command"], cwd_resolved, int(timeout))
    t = threading.Thread(target=target, args=args, name=f"run-{run_id}", daemon=True)
    t.start()
    return run_id

"""scheduler job 业务实现：进程内直调（区别于 dividend 的 HTTP self-call）

- job 静态定义（JOB_SPECS）在此注册；cron 来源是 config/app.yaml（manager 组装）
- enabled 状态来源是 data/scheduler/enabled.json（manager 读写）
- _process_lock 是唯一处理锁：定时触发、页面立即执行、旧 /api/process/pending 共用，
  避免并发处理同一批 pending 重复消耗 ASR 配额。endpoints 单向 import 本文件，无循环依赖。
"""

import asyncio
from typing import Any

from loguru import logger

# 处理任务锁：避免并发触发同一批 pending 被处理两次（重复消耗 ASR 配额）。
# endpoints 旧手动路径与 scheduler 路径（cron / trigger_now）共用此锁。
_process_lock = asyncio.Lock()

# 任务静态定义（id/name/target/description）。crons 由 manager 从 app.yaml 读取后合并，
# enabled 由 manager 从 enabled.json overlay 读取后合并。
JOB_SPECS: list[dict[str, str]] = [
    {
        "id": "process_pending",
        "name": "转写待处理视频",
        "target": "process_pending",
        "description": "处理 status=pending 视频：阿里 FunASR 转写 → unread（每天 09:45 / 17:15）",
    },
    {
        "id": "cleanup_old_records",
        "name": "清理过期记录",
        "target": "cleanup",
        "description": "删除超过保留期的 wav 源文件与 status/output 记录（每天 03:07）",
    },
]


async def run_process_pending(services: dict, job_id: str, trigger: str = "scheduled") -> dict[str, Any]:
    """转写 status=pending 视频（阿里 FunASR → unread）。

    Returns:
        {"status": success|failed|skipped, "count": 成功数, "failed": 失败数, "reason"?}
    """
    processor = services.get("processor")
    if processor is None:
        return {"status": "failed", "error": "processor 未初始化"}

    pending = await processor.status_manager.list_pending()
    if not pending:
        return {"status": "skipped", "reason": "no_pending", "count": 0}

    if _process_lock.locked():
        # 已有处理在跑（手动撞定时或反之）：记 skipped，不重复消耗 ASR 配额
        return {"status": "skipped", "reason": "process_busy", "count": 0}

    async with _process_lock:
        result = await processor.process_pending()

    status = "success" if result.get("failed", 0) == 0 else "failed"
    payload: dict[str, Any] = {
        "status": status,
        "count": result.get("success"),
        "failed": result.get("failed"),
    }
    if result.get("failed"):
        payload["reason"] = f"{result.get('failed')} 个视频转写失败，详见服务日志"
    return payload


async def run_cleanup(services: dict, job_id: str, trigger: str = "scheduled") -> dict[str, Any]:
    """清理超过保留期的记录：删 status.json 记录 + 对应 wav 源文件 + output json。

    与旧 main._scheduled_cleanup 同源逻辑；lifespan 启动时的立即清理也复用本函数
    （trigger="startup"，不写 scheduler 历史）。

    Returns:
        {"status": success|failed, "count": 删除文件数, "reason"?, "failed"?}
    """
    processor = services.get("processor")
    if processor is None:
        return {"status": "failed", "error": "processor 未初始化"}

    days = int(services.get("cleanup_days", 45))
    deleted_ids = await processor.status_manager.cleanup_old_records(days)
    if not deleted_ids:
        logger.info(f"清理:无过期记录(>{days}d)")
        return {"status": "success", "reason": f"无过期记录(>{days}d)", "count": 0}

    success = 0
    failed_files: list[str] = []
    for aid in deleted_ids:
        audio_filename = f"{aid}.wav"
        ok = await processor.filesystem_client.delete_file(audio_filename)
        if ok:
            success += 1
        else:
            failed_files.append(audio_filename)
        # 同步清 output json（data/output/{aweme_id}.json），与 status.json 保持一致
        try:
            (processor.output_dir / f"{aid}.json").unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"清 output json 失败 {aid}: {e}")

    payload: dict[str, Any] = {"count": success}
    if failed_files:
        payload.update(
            {
                "status": "failed",
                "failed": failed_files,
                "reason": f"{len(failed_files)} 个 wav 删除失败",
            }
        )
    else:
        payload["status"] = "success"
    logger.info(f"清理完成:删 {success}/{len(deleted_ids)} 个文件(>{days}d),失败 {failed_files}")
    return payload


# target 注册表：manager._execute_job 按此分发。签名统一 (services, job_id, trigger)。
JOB_TARGETS: dict[str, Any] = {
    "process_pending": run_process_pending,
    "cleanup": run_cleanup,
}

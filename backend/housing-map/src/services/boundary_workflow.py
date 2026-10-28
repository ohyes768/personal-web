"""小区轮廓生成工作流:任务、候选预览、人工确认覆盖层与撤销。

数据分层:
  基础层  binjiang_polygons_merged.json(由 OSM 重建/旧导入写入,本服务只读)
  覆盖层  boundary_workflow.sqlite3 的 overrides 表(人工确认结果,独立存放)

地图查询用"基础 + 覆盖"的有效视图;后台重建基础层不会吞掉人工确认结果,撤销只删除覆盖层,
不把历史基础快照写回。版本判定(revision)只覆盖当前小区的基础条目、覆盖条目与有效定位,
不用全文件哈希,避免无关小区改动引起冲突。
"""
from __future__ import annotations

import hashlib
import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone

from src.services import boundary_workflow_store as store_module
from src.services.boundary_estimate import (
    ALGORITHM_VERSION,
    QUERY_VERSION,
    EstimateError,
    EstimateTarget,
    aliases_from_source,
    canonical_aliases,
    estimate_one,
    member_ring_gcj02,
    normalize_place_name,
)
from src.services.boundary_geometry import validate_rings
from src.services.boundary_publish import publish_lock
from src.services.boundary_workflow_store import BoundaryWorkflowStore
from src.services.community_filters import MERGE_DROP_IDS
from src.services.data_loader import load_coordinates, load_display_communities, load_polygons

logger = logging.getLogger("housing-map")

MAX_QUEUE = 20  # 最多 20 个等待任务


class WorkflowError(Exception):
    """带 HTTP 语义的工作流错误。"""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# 单例:存储与执行器
# ---------------------------------------------------------------------------

_store_instance: BoundaryWorkflowStore | None = None
_store_path = None
_executor_instance: "WorkflowExecutor | None" = None
_executor_lock = threading.Lock()


def _store() -> BoundaryWorkflowStore:
    global _store_instance, _store_path
    path = store_module.WORKFLOW_DB
    if _store_instance is None or _store_path != path:
        _store_instance = BoundaryWorkflowStore(path)
        _store_path = path
    return _store_instance


def _executor() -> "WorkflowExecutor":
    global _executor_instance
    with _executor_lock:
        if _executor_instance is None:
            _executor_instance = WorkflowExecutor(_run_job, max_queue=MAX_QUEUE)
            _executor_instance.start()
        return _executor_instance


class WorkflowExecutor:
    """单执行器:串行 FIFO,队列有界。首版单实例单 worker,不引入分布式队列。"""

    def __init__(self, worker, *, max_queue: int = MAX_QUEUE):
        self._worker = worker
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="boundary-workflow", daemon=True)
                self._thread.start()

    def submit(self, job_id: str) -> bool:
        """入队;队列已满返回 False。"""
        try:
            self._queue.put_nowait(job_id)
            return True
        except queue.Full:
            return False

    def pending(self) -> int:
        return self._queue.qsize()

    def shutdown(self) -> None:
        self._queue.put_nowait(None)  # type: ignore[arg-type]

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                if job_id is None:
                    return
                self._worker(job_id)
            except Exception:  # noqa: BLE001 - 单个任务失败不能拖垮执行器
                logger.exception("轮廓工作流任务执行失败: %s", job_id)
            finally:
                self._queue.task_done()


def recover_interrupted_jobs() -> int:
    """启动恢复:在途任务标记中断,不自动重新向外网发请求。"""
    try:
        return _store().interrupt_stale_jobs()
    except Exception:  # noqa: BLE001 - 恢复失败不应阻断服务启动
        logger.exception("轮廓工作流启动恢复失败")
        return 0


# ---------------------------------------------------------------------------
# 有效视图与版本判定
# ---------------------------------------------------------------------------

def is_displayable(entry) -> bool:
    """条目是否可作为正式轮廓展示(与地图渲染口径一致)。

    无条目、无 rings、或来源为 shp(数据管线保留但不展示)都算缺口。
    """
    if not entry or not isinstance(entry, dict):
        return False
    if not entry.get("rings"):
        return False
    return entry.get("source") != "shp"


def effective_polygons() -> dict[str, dict]:
    """基础轮廓 + 人工确认覆盖层 = 地图使用的有效轮廓视图。"""
    base = load_polygons()
    try:
        overrides = _store().all_overrides()
    except Exception:  # noqa: BLE001 - 工作流库缺失时按只有基础层处理
        logger.exception("读取轮廓覆盖层失败,按基础层返回")
        return dict(base)
    result = dict(base)
    for cid, override in overrides.items():
        result[cid] = {
            "source": override["source"],
            "rings": json.loads(override["rings"]),
            "confirmed_at": override["confirmed_at"],
            "candidate_id": override["candidate_id"],
        }
    return result


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     default=str).encode()).hexdigest()[:10]


def community_context(cid: str) -> dict | None:
    """小区在展示集合中的上下文:名称与 GCJ02 坐标。已不在展示集合返回 None。"""
    communities = load_display_communities(drop_ids=MERGE_DROP_IDS)
    match = next((c for c in communities if str(c.get("community_id")) == str(cid)), None)
    if match is None:
        return None
    coordinate = (load_coordinates() or {}).get(str(cid)) or {}
    longitude = coordinate.get("longitude")
    latitude = coordinate.get("latitude")
    if not longitude or not latitude:
        return None
    alias = match.get("community_alias") or ""
    if not isinstance(alias, str):
        alias = ""
    return {
        "community_id": str(cid),
        "community_name": match.get("community_name") or "",
        "community_alias": alias.strip(),
        "longitude": float(longitude),
        "latitude": float(latitude),
    }


def base_revision(cid: str, context: dict | None = None) -> str:
    """基础层 + 定位的版本指纹(不含人工覆盖层)。"""
    entry = load_polygons().get(str(cid))
    context = context or community_context(cid) or {}
    position = [round(context.get("longitude") or 0, 6), round(context.get("latitude") or 0, 6),
                context.get("community_name") or ""]
    return _digest({"base": entry, "position": position})


def _effective_revision_for(base_entry, override, position) -> str:
    """有效层版本指纹的纯函数: 基础条目 + 人工覆盖 + 定位。"""
    return _digest({"base": base_entry, "override": override, "position": position})


def _position_of(context: dict) -> list:
    return [round(context.get("longitude") or 0, 6), round(context.get("latitude") or 0, 6),
            context.get("community_name") or ""]


def effective_revision(cid: str, context: dict | None = None) -> str:
    """有效层(基础 + 人工覆盖 + 定位)的版本指纹。"""
    context = context or community_context(cid) or {}
    override = None
    try:
        row = _store().override(str(cid))
    except Exception:  # noqa: BLE001
        row = None
    if row:
        override = {"candidate_id": row["candidate_id"], "revision": row["revision"],
                    "rings": json.loads(row["rings"])}
    return _effective_revision_for(load_polygons().get(str(cid)), override, _position_of(context))


def input_fingerprint(cid: str, context: dict) -> str:
    """生成输入指纹:主名、别名、坐标、查询版本和算法版本。"""
    primary = context.get("community_name") or ""
    return _digest({
        "community_id": str(cid),
        "longitude": round(context["longitude"], 6),
        "latitude": round(context["latitude"], 6),
        "name": normalize_place_name(primary),
        "aliases": canonical_aliases(primary, aliases_from_source(context.get("community_alias"))),
        "query_version": QUERY_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
    })


# ---------------------------------------------------------------------------
# 任务
# ---------------------------------------------------------------------------

def create_estimate(cid: str, *, regenerate: bool = False, refresh_buildings: bool = False) -> tuple[int, dict]:
    """发起或复用一次轮廓估算任务。

    返回 (http_status, payload)。新任务 202,复用已有任务/候选 200。
    """
    cid = str(cid)
    context = community_context(cid)
    if context is None:
        raise WorkflowError(404, "community_not_found", "小区不存在或已不在展示集合")
    store = _store()
    fingerprint = input_fingerprint(cid, context)

    if not regenerate and not refresh_buildings:
        active = store.active_job(cid, fingerprint)
        if active:
            return 200, {"job_id": active["job_id"], "phase": active["phase"],
                         "reused": True, "candidate_id": active.get("candidate_id")}
        ready = store.ready_candidate(cid)
        if ready and ready.get("input_fingerprint") == fingerprint:
            return 200, {"candidate_id": ready["candidate_id"], "job_id": ready["job_id"],
                         "phase": "succeeded", "reused": True}

    # 重新生成,或旧 ready 的输入指纹已对不上:旧候选置为 superseded
    store.supersede_ready_candidates(cid)

    job_id = uuid.uuid4().hex
    store.insert_job(job_id, cid, fingerprint, refresh_buildings=refresh_buildings)
    if not _executor().submit(job_id):
        store.update_job(job_id, phase="failed", error_code="queue_full",
                         error_message="生成队列已满,请稍后重试")
        raise WorkflowError(409, "queue_full", "生成队列已满,请稍后重试")
    return 202, {"job_id": job_id, "phase": "queued", "reused": False}


def _run_job(job_id: str) -> None:
    """执行器回调:生成候选。失败按错误类别落库,不抛到执行器。"""
    store = _store()
    job = store.job(job_id)
    if job is None:
        return
    cid = job["community_id"]
    context = community_context(cid)
    if context is None or input_fingerprint(cid, context) != job["input_fingerprint"]:
        store.update_job(job_id, phase="failed", error_code="stale",
                         error_message="生成输入已变化,任务未发布")
        return

    def progress(phase: str, detail: str = "") -> None:
        store.update_job(job_id, phase=phase)

    target = EstimateTarget(
        community_id=cid, community_name=context["community_name"],
        longitude=context["longitude"], latitude=context["latitude"],
        aliases=aliases_from_source(context.get("community_alias")),
    )
    try:
        outcome = estimate_one(target, progress=progress,
                               use_cache=not bool(job.get("refresh_buildings")))
    except EstimateError as exc:
        store.update_job(job_id, phase="failed", error_code=exc.code, error_message=exc.message)
        return
    except Exception as exc:  # noqa: BLE001 - 单个任务失败不拖垮执行器
        logger.exception("轮廓估算失败: %s", cid)
        store.update_job(job_id, phase="failed", error_code="internal", error_message=str(exc))
        return

    reason = validate_rings([outcome.ring])
    if reason:
        store.update_job(job_id, phase="failed", error_code="invalid_geometry", error_message=reason)
        return

    reference = [{"kind": m.kind, "rings": [member_ring_gcj02(m)]} for m in outcome.members]
    candidate_id = uuid.uuid4().hex
    with publish_lock():
        context_now = community_context(cid)
        if context_now is None or input_fingerprint(cid, context_now) != job["input_fingerprint"]:
            context_now = None
        else:
            base_rev = base_revision(cid, context_now)
            effective_rev = effective_revision(cid, context_now)
    if context_now is None:
        store.update_job(job_id, phase="failed", error_code="stale",
                         error_message="生成输入已变化,任务未发布")
        return
    store.complete_job_with_candidate(
        job_id=job_id, candidate_id=candidate_id, community_id=cid,
        fingerprint=job["input_fingerprint"], base_revision=base_rev, effective_revision=effective_rev,
        rings=[outcome.ring], reference_buildings=reference, area_ha=outcome.area_ha,
        building_faces=outcome.building_faces, residential_faces=outcome.residential_faces,
        low_confidence=outcome.low_confidence, source="osm-building", warnings=list(outcome.warnings),
        estimated_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )


def job_state(job_id: str) -> dict:
    job = _store().job(job_id)
    if job is None:
        raise WorkflowError(404, "job_not_found", "任务不存在")
    return {
        "job_id": job["job_id"],
        "community_id": job["community_id"],
        "phase": job["phase"],
        "error_code": job["error_code"],
        "error_message": job["error_message"],
        "candidate_id": job["candidate_id"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


# ---------------------------------------------------------------------------
# 候选
# ---------------------------------------------------------------------------

def candidate_state(candidate_id: str) -> dict:
    candidate = _store().candidate(candidate_id)
    if candidate is None:
        raise WorkflowError(404, "candidate_not_found", "候选不存在")
    cid = candidate["community_id"]
    context = community_context(cid)
    current_effective = effective_revision(cid, context)
    current_base = base_revision(cid, context)
    stale_reasons = []
    if not context:
        stale_reasons.append("小区已不在展示集合")
    elif candidate.get("input_fingerprint") != input_fingerprint(cid, context):
        stale_reasons.append("生成输入已变化")
    if candidate["base_revision"] != current_base:
        stale_reasons.append("基础轮廓或定位已变化")
    if candidate["status"] == "ready" and candidate["effective_revision"] != current_effective:
        stale_reasons.append("当前轮廓状态已变化")
    return {
        "candidate_id": candidate["candidate_id"],
        "job_id": candidate["job_id"],
        "community_id": cid,
        "community_name": (context or {}).get("community_name") or "",
        "status": candidate["status"],
        "rings": json.loads(candidate["rings"]),
        "reference_buildings": json.loads(candidate["reference_buildings"]),
        "area_ha": candidate["area_ha"],
        "building_faces": candidate["building_faces"],
        "residential_faces": candidate["residential_faces"],
        "low_confidence": bool(candidate["low_confidence"]),
        "source": candidate["source"],
        "warnings": json.loads(candidate["warnings"]),
        "estimated_at": candidate["estimated_at"],
        "created_at": candidate["created_at"],
        "revision": current_effective,
        "base_revision": candidate["base_revision"],
        "current_base_revision": current_base,
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "applicable": candidate["status"] == "ready" and not stale_reasons,
        "position": ([context["longitude"], context["latitude"]] if context else None),
    }


def community_state(cid: str) -> dict:
    """小区的工作流概览:有效轮廓、版本、当前任务/候选、可撤销操作。"""
    cid = str(cid)
    context = community_context(cid)
    if context is None:
        raise WorkflowError(404, "community_not_found", "小区不存在或已不在展示集合")
    store = _store()
    polygons = load_polygons()
    base_entry = polygons.get(cid)
    override = store.override(cid)
    ready = store.ready_candidate(cid)
    latest_job = store.latest_job(cid)
    active = store.active_job(cid, input_fingerprint(cid, context))
    apply_operation = store.latest_operation(cid, "apply")
    revertable = None
    if override and apply_operation and apply_operation["candidate_id"] == override["candidate_id"]:
        revertable = {
            "operation_id": apply_operation["operation_id"],
            "candidate_id": override["candidate_id"],
            "confirmed_at": override["confirmed_at"],
        }
    effective = effective_polygons().get(cid)
    return {
        "community_id": cid,
        "community_name": context["community_name"],
        "position": [context["longitude"], context["latitude"]],
        "revision": effective_revision(cid, context),
        "has_visible_boundary": is_displayable(effective),
        "boundary_source": (effective or {}).get("source"),
        "boundary_confirmed_at": (effective or {}).get("confirmed_at"),
        "base_has_boundary": is_displayable(base_entry),
        "override": None if not override else {
            "candidate_id": override["candidate_id"],
            "confirmed_at": override["confirmed_at"],
            "revision": override["revision"],
            "source": override["source"],
        },
        "job": None if not active else {
            "job_id": active["job_id"], "phase": active["phase"],
            "created_at": active["created_at"], "updated_at": active["updated_at"],
        },
        "latest_job": None if not latest_job else {
            "job_id": latest_job["job_id"], "phase": latest_job["phase"],
            "error_code": latest_job["error_code"], "error_message": latest_job["error_message"],
            "created_at": latest_job["created_at"],
        },
        "candidate": None if not ready else {
            "candidate_id": ready["candidate_id"], "status": ready["status"],
            "area_ha": ready["area_ha"], "low_confidence": bool(ready["low_confidence"]),
            "created_at": ready["created_at"],
        },
        "revertable": revertable,
    }


# ---------------------------------------------------------------------------
# 拒绝 / 应用 / 撤销
# ---------------------------------------------------------------------------

def _replay(store, operation_id: str, community_id: str, kind: str) -> dict | None:
    """幂等:同一 operation_id 的同一操作重放原结果。

    只比对小区与操作类型 —— 候选在 apply 时已知、在 revert 时由当前覆盖层决定,
    两者都在各自的流程里另行核对。"""
    existing = store.operation(operation_id)
    if existing is None:
        return None
    if existing["community_id"] != community_id or existing["kind"] != kind:
        raise WorkflowError(409, "operation_conflict", "该 operation_id 已用于另一项操作")
    return json.loads(existing["result"])


def reject_candidate(candidate_id: str, expected_revision: str) -> dict:
    """标记候选范围不合适。只处理当前 ready 候选,不撤销已应用结果。"""
    store = _store()
    candidate = store.candidate(candidate_id)
    if candidate is None:
        raise WorkflowError(404, "candidate_not_found", "候选不存在")
    cid = candidate["community_id"]
    if candidate["status"] == "rejected":
        return {"candidate_id": candidate_id, "community_id": cid, "status": "rejected"}
    if candidate["status"] != "ready":
        raise WorkflowError(409, "candidate_state_conflict", "该候选已不在待应用状态")
    if expected_revision and expected_revision != effective_revision(cid):
        raise WorkflowError(409, "revision_conflict", "当前轮廓状态已变化,请刷新后重新核对")
    store.set_candidate_status(candidate_id, "rejected")
    return {"candidate_id": candidate_id, "community_id": cid, "status": "rejected"}


def apply_candidate(candidate_id: str, expected_revision: str, operation_id: str) -> dict:
    """应用候选:写入人工覆盖层,不改写基础轮廓文件。"""
    store = _store()
    candidate = store.candidate(candidate_id)
    if candidate is None:
        raise WorkflowError(404, "candidate_not_found", "候选不存在")
    cid = candidate["community_id"]

    replay = _replay(store, operation_id, cid, "apply")
    if replay is not None:
        if replay.get("candidate_id") != candidate_id:
            raise WorkflowError(409, "operation_conflict", "该 operation_id 已用于另一项操作")
        return replay

    if candidate["status"] != "ready":
        raise WorkflowError(409, "candidate_state_conflict", "该候选已不在待应用状态")
    context = community_context(cid)
    if context is None:
        raise WorkflowError(404, "community_not_found", "小区已不在展示集合,不能继续应用候选")

    rings = json.loads(candidate["rings"])
    reason = validate_rings(rings)
    if reason:
        raise WorkflowError(422, "invalid_geometry", reason)

    with publish_lock():
        context = community_context(cid)
        if context is None:
            raise WorkflowError(404, "community_not_found", "小区已不在展示集合,不能继续应用候选")
        current_base = base_revision(cid, context)
        current_effective = effective_revision(cid, context)
        if candidate.get("input_fingerprint") != input_fingerprint(cid, context):
            raise WorkflowError(409, "candidate_stale", "生成输入已变化,请重新生成候选")
        if candidate["base_revision"] != current_base:
            raise WorkflowError(409, "candidate_stale", "基础轮廓或定位已变化,请重新生成候选")
        if expected_revision and expected_revision != current_effective:
            raise WorkflowError(409, "revision_conflict", "当前轮廓状态已变化,请刷新后重新核对")
        previous = store.override(cid)
        superseded = previous["candidate_id"] if previous and previous["candidate_id"] != candidate_id else None
        # 提交后的 revision 可以先算出来(覆盖层的 revision 号是前一条 +1),
        # 于是覆盖层、候选状态、操作记录能在同一个事务里落库, 不留半截状态。
        next_override = {"candidate_id": candidate_id,
                         "revision": (previous["revision"] + 1) if previous else 1,
                         "rings": rings}
        after_revision = _effective_revision_for(
            load_polygons().get(cid), next_override, _position_of(context))
        result = {
            "candidate_id": candidate_id,
            "community_id": cid,
            "operation_id": operation_id,
            "revision": after_revision,
            "previous_revision": current_effective,
            "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        store.apply_candidate_atomic(
            community_id=cid, candidate_id=candidate_id, rings=rings, source=candidate["source"],
            operation_id=operation_id, before_revision=current_effective,
            after_revision=after_revision, result=result, supersede_candidate_id=superseded,
        )
    return result


def revert_community(cid: str, expected_revision: str, apply_operation_id: str, operation_id: str) -> dict:
    """撤销人工确认的轮廓:只删除覆盖层,不把历史基础快照写回。"""
    cid = str(cid)
    store = _store()
    replay = _replay(store, operation_id, cid, "revert")
    if replay is not None:
        return replay

    override = store.override(cid)
    if override is None:
        raise WorkflowError(409, "nothing_to_revert", "该小区当前没有人工确认的轮廓")
    apply_operation = store.operation(apply_operation_id)
    if apply_operation is None or apply_operation["kind"] != "apply":
        raise WorkflowError(409, "apply_operation_not_found", "找不到对应的应用操作记录")
    if apply_operation["candidate_id"] != override["candidate_id"]:
        raise WorkflowError(409, "apply_operation_mismatch", "应用操作与当前人工轮廓不匹配")

    context = community_context(cid)
    with publish_lock():
        current_effective = effective_revision(cid, context)
        if expected_revision and expected_revision != current_effective:
            raise WorkflowError(409, "revision_conflict", "当前轮廓状态已变化,请刷新后重新核对")
        # 撤销后回到"无覆盖层"的视图, revision 可以先算出来
        after_revision = _effective_revision_for(
            load_polygons().get(cid), None, _position_of(context))
        result = {
            "community_id": cid,
            "operation_id": operation_id,
            "candidate_id": override["candidate_id"],
            "revision": after_revision,
            "previous_revision": current_effective,
            "reverted_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        store.revert_candidate_atomic(
            community_id=cid, candidate_id=override["candidate_id"], operation_id=operation_id,
            before_revision=current_effective, after_revision=after_revision, result=result,
        )
    return result

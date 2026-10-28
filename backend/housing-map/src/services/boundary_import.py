"""轮廓导入落盘:备份轮转 + 原子写,仅覆盖导入条目,不触碰既有轮廓。"""
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.services.boundary_publish import publish_lock
from src.services.data_loader import DATA_DIR

POLYGONS_PATH = DATA_DIR / "binjiang_polygons_merged.json"
BACKUP_DIR = DATA_DIR / "boundaries-backup"
MAX_BACKUPS = 5


def rotate_backup(path: Path, backup_dir: Path | None = None, keep: int = MAX_BACKUPS) -> Path | None:
    backup_dir = backup_dir or BACKUP_DIR
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = backup_dir / f"{path.stem}.{stamp}{path.suffix}"
    shutil.copy2(path, target)
    stale = sorted(backup_dir.glob(f"{path.stem}.*{path.suffix}"))
    for extra in stale[:-keep]:
        extra.unlink()
    return target


def merge_boundaries(items: list[dict], path: Path | None = None, backup_dir: Path | None = None) -> None:
    """items 须已通过路由层校验;同 cid 覆盖(幂等),_meta 追加 osm-building 计数。"""
    path = Path(path or POLYGONS_PATH)
    backup_dir = backup_dir or BACKUP_DIR
    # 与重建、人工覆盖操作共用发布锁:写基础层时不会与版本判定交错
    with publish_lock():
        data = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        rotate_backup(path, backup_dir)
        matched = meta.get("matched") if isinstance(meta.get("matched"), dict) else {}
        for item in items:
            entry = {"source": item["source"], "rings": item["rings"]}
            if item.get("meta"):
                entry.update(item["meta"])
            data[item["community_id"]] = entry
            if item["source"] == "osm-building":
                matched["osm-building"] = matched.get("osm-building", 0) + 1
        if items:
            meta["matched"] = matched
            description = "小区边界轮廓合并数据 (GCJ-02)"
            meta.setdefault("description", description)
            sources = meta.get("sources")
            note = "OpenStreetMap building clusters (estimated)"
            if isinstance(sources, list) and note not in sources:
                sources.append(note)
            elif not isinstance(sources, list):
                meta["sources"] = [note]
            data["_meta"] = meta
        fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

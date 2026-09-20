"""人工校验的挂牌行情参考快照读取与校验。"""

import json
from datetime import date
from pathlib import Path

from src.services.data_loader import DATA_DIR


MARKET_REFERENCE_PATH = DATA_DIR / "market_reference.json"


def _unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_valid_snapshot(snapshot: object) -> bool:
    if not isinstance(snapshot, dict) or snapshot.get("price_kind") != "listing_reference":
        return False

    source = snapshot.get("source")
    overall = snapshot.get("overall")
    subdistricts = snapshot.get("subdistricts")
    if not isinstance(source, dict) or not isinstance(overall, dict) or not isinstance(subdistricts, list):
        return False
    if not isinstance(source.get("name"), str) or not source["name"].strip():
        return False
    if not isinstance(source.get("url"), str) or not source["url"].startswith("https://"):
        return False
    if not isinstance(source.get("captured_at"), str):
        return False
    try:
        date.fromisoformat(source["captured_at"])
    except ValueError:
        return False
    if not isinstance(overall.get("avg_price"), int) or overall["avg_price"] <= 0:
        return False
    if not all(_is_number(overall.get(key)) for key in ("mom_percent", "yoy_percent")):
        return False

    for row in subdistricts:
        if not isinstance(row, dict):
            return False
        if not all(isinstance(row.get(key), str) and row[key].strip() for key in ("name", "map_subdistrict", "map_scope_note")):
            return False
        if not isinstance(row.get("avg_price"), int) or row["avg_price"] <= 0:
            return False
        if not _is_number(row.get("mom_percent")):
            return False
    return bool(subdistricts)


def load_market_reference(path: Path | None = None) -> dict:
    """返回可安全展示的挂牌参考快照；缺失或无效快照不伪造行情数据。"""
    source_path = path or MARKET_REFERENCE_PATH
    try:
        snapshot = json.loads(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _unavailable("missing_snapshot")
    except (OSError, json.JSONDecodeError, ValueError):
        return _unavailable("invalid_snapshot")

    if not _is_valid_snapshot(snapshot):
        return _unavailable("invalid_snapshot")
    return {"available": True, **snapshot}

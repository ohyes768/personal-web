"""法拍独立存储；OS文件锁跨进程互斥，原子替换保留旧数据。"""
import json
import os
import tempfile
from pathlib import Path

from src.services.data_loader import DATA_DIR

AUCTION_PATH = DATA_DIR / "auction_records.json"


class StoreLock:
    def __init__(self, path):
        self.path = Path(str(path) + ".lock")
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if self.path.stat().st_size == 0:
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise BlockingIOError("auction collection is already running") from exc
        return self

    def __exit__(self, *args):
        # OS releases the lock on close/crash; the sidecar is deliberately retained.
        self.file.close()


def read_store(path=AUCTION_PATH):
    path = Path(path)
    if not path.exists():
        return {"version": 1, "records": [], "last_run": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("records"), list):
        raise ValueError("invalid auction store")
    if any(not isinstance(row, dict) or not row.get("source") or not row.get("auction_id") for row in data["records"]):
        raise ValueError("invalid auction records")
    return data


def write_store(path, rows, result):
    old = read_store(path)
    merged = {(r["source"], r["auction_id"]): r for r in old["records"]}
    merged.update({(r["source"], r["auction_id"]): r for r in rows})
    payload = {"version": 1, "records": list(merged.values()), "last_run": result}
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

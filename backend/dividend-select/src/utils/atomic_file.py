"""Publish complete files on the same filesystem, preserving the old file on failure."""
import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, writer):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        writer(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_csv(df, path: Path):
    atomic_write(path, lambda temporary: df.to_csv(temporary, index=False, encoding='utf-8-sig'))

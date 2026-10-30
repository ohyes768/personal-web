"""Bounded read projections, invalidated by durable DB and input-file versions."""
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from threading import RLock


class ProjectionCache:
    def __init__(self, capacity=8):
        self.capacity = capacity
        self._entries = OrderedDict()
        self._lock = RLock()

    @staticmethod
    def _version(paths):
        versions = []
        for path in paths:
            try:
                stat = path.stat()
            except FileNotFoundError:
                versions.append(None)
            else:
                versions.append((stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        return tuple(versions)

    def read(self, paths, build, *, variant=None):
        paths = tuple(Path(path).resolve() for path in paths)
        key = paths, variant
        # Single-flight construction prevents overlapping status polls and catalog
        # requests from each rebuilding the same version. No network calls here.
        with self._lock:
            version = self._version(paths)
            cached = self._entries.get(key)
            if cached is not None and cached[0] == version:
                self._entries.move_to_end(key)
                value = cached[1]
            else:
                value = build()
                # A writer may commit while the projection spans multiple reads.
                # Return that ordinary read, but never retain it for later callers.
                if self._version(paths) == version:
                    self._entries[key] = version, value
                    self._entries.move_to_end(key)
                    while len(self._entries) > self.capacity:
                        self._entries.popitem(last=False)
            # Callers enrich/mutate nested sources and positions; cache owns value.
            return deepcopy(value)


def projection_inputs(store, data_dir):
    data_dir = Path(data_dir)
    return (store.path, Path(str(store.path) + '-wal'),
            data_dir / 'property_types.json', data_dir / 'binjiang_coordinates.json')

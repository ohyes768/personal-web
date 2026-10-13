"""Serialize source preparation and link writes within the single service worker."""
from functools import wraps
from threading import RLock

operation_lock = RLock()


def serialized(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        with operation_lock:
            return function(*args, **kwargs)
    return wrapper

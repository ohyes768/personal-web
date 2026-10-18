"""Shared, cancellable Fang request budget. State survives clients and restarts."""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import logging
import math
import threading
import time
from pathlib import Path

from src.services.rental_reference.storage import RentalPublishLock, _atomic_write_json

logger = logging.getLogger(__name__)


class FangChallenge(ValueError):
    """Upstream explicitly requires human verification."""


class FangCoolingDown(FangChallenge):
    def __init__(self, until):
        self.until = until
        label = dt.datetime.fromtimestamp(until, dt.UTC).isoformat()
        super().__init__(f'房天下验证冷却中，暂停访问至 {label}')


class FangRequestCancelled(InterruptedError):
    pass


class FangTemporarilyUnavailable(RuntimeError):
    pass


class FangRequestPolicy:
    def __init__(self, directory: Path, *, cancel_event=None, clock=time.time,
                 wait=None, interval=5.0):
        self.path = Path(directory) / 'fang_request_state.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cancel_event = cancel_event or threading.Event()
        self.clock = clock
        self.wait = wait or self.cancel_event.wait
        self.interval = interval
        self.request_count = 0
        self.stopped = False

    def _wait(self, seconds):
        if self.cancel_event.is_set() or (seconds > 0 and self.wait(seconds)):
            raise FangRequestCancelled('房天下请求已取消')

    @contextlib.contextmanager
    def locked(self):
        lock = RentalPublishLock(self.path.with_suffix(''))
        while True:
            self._wait(0)
            try:
                lock.__enter__()
                break
            except BlockingIOError:
                self._wait(0.1)
        try:
            yield
        finally:
            lock.__exit__(None, None, None)

    def _read(self):
        default = dict(version=1, challenge_level=0, cooldown_until=0, last_request_at=0)
        try:
            state = json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(state, dict) or state.get('version') != 1
                    or any(not isinstance(state.get(k), (int, float))
                           or not math.isfinite(state[k]) or state[k] < 0
                           for k in ('challenge_level', 'cooldown_until', 'last_request_at'))
                    or state['challenge_level'] not in (0, 1, 2, 3)):
                raise ValueError('invalid state')
            return state
        except FileNotFoundError:
            return default
        except (OSError, ValueError, TypeError):
            logger.warning('Fang request state unreadable; pausing conservatively', exc_info=True)
            default['cooldown_until'] = self.clock() + 3600
            _atomic_write_json(self.path, default)
            return default

    def status(self):
        with self.locked():
            return self._read()

    def mark_complete(self):
        with self.locked():
            state = self._read()
            # A different worker may have encountered a challenge meanwhile.
            if state['cooldown_until'] <= self.clock():
                state.update(challenge_level=0, cooldown_until=0)
                _atomic_write_json(self.path, state)

    def perform(self, action):
        """Serialize each HTTP hop and retry only actual timeouts, once."""
        if self.stopped:
            raise FangTemporarilyUnavailable('房天下连续超时，本轮暂停访问')
        for attempt in range(2):
            with self.locked():
                state = self._read()
                if state['cooldown_until'] > self.clock():
                    raise FangCoolingDown(state['cooldown_until'])
                self._wait(max(0, state['last_request_at'] + self.interval - self.clock()))
                self.request_count += 1
                try:
                    return action()
                except FangChallenge:
                    level = min(3, int(state['challenge_level']) + 1)
                    state.update(challenge_level=level,
                                 cooldown_until=self.clock() + (3600, 21600, 86400)[level - 1])
                    raise
                except Exception as exc:
                    from curl_cffi.requests.exceptions import Timeout
                    if not isinstance(exc, (TimeoutError, Timeout)):
                        raise
                    if attempt:
                        self.stopped = True
                        raise FangTemporarilyUnavailable('房天下连续超时，本轮暂停访问') from exc
                finally:
                    state['last_request_at'] = self.clock()
                    _atomic_write_json(self.path, state)
            self._wait(30)

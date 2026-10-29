"""Shared request transport for Xingfuli's public Hangzhou pages.

The rent collector and the source-discovery adapter must share one rate limit,
one cooldown and one cancellation slot. Two writers inside the same data
directory would otherwise exceed what the platform tolerates.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from src.services.fang_rentals import RentalCrawlCancelled
from src.services.rental_reference.storage import RentalPublishLock, _atomic_write_json


DEFAULT_XINGFULI_DELAY = 3


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Redirects often lead to login/challenge; never follow an unchecked URL.
        return None


class XingfuliTransport:
    """Bounded, serialized HTTP access to the whitelisted Xingfuli host."""

    def __init__(self, timeout=20, *, directory=None, fetcher=None, delay=DEFAULT_XINGFULI_DELAY, cancel_event=None, validate=None):
        if directory is None:
            from src.services.data_loader import DATA_DIR
            directory = DATA_DIR / 'rentals'
        self.directory = Path(directory)
        self.timeout = timeout
        self.delay = max(0, delay) if fetcher else max(DEFAULT_XINGFULI_DELAY, delay)
        self.cancel = cancel_event or threading.Event()
        self.fetcher = fetcher
        self.request_count = 0
        self.wait_seconds = 0
        self.http_seconds = 0
        self.cooldown_until = None
        self.opener = build_opener(_NoRedirect())
        self.validate = validate

    def _check_cancel(self, seconds=0):
        if self.cancel.is_set() or (seconds and self.cancel.wait(seconds)):
            raise RentalCrawlCancelled([], None)

    def fetch(self, url):
        if self.validate:
            self.validate(url)
        self._check_cancel()
        # Serializes HTTP across same-data-directory workers/processes.
        with RentalPublishLock(self.directory / 'xingfuli_request'):
            path = self.directory / 'xingfuli_request_state.json'
            if path.exists():
                try:
                    state = json.loads(path.read_text(encoding='utf-8'))
                    last, cooldown = float(state['last_request_at']), float(state['cooldown_until'])
                    if not all(math.isfinite(v) and v >= 0 for v in (last, cooldown)):
                        raise ValueError('invalid state')
                except (ValueError, KeyError, TypeError):
                    raise ValueError('幸福里请求状态损坏，请核查后重试') from None
            else:
                last, cooldown = 0, 0
            if cooldown > time.time():
                self.cooldown_until = dt.datetime.fromtimestamp(cooldown, dt.UTC).isoformat()
                raise ValueError('幸福里来源冷却中，暂停请求')
            waiting = time.monotonic()
            try:
                self._check_cancel(max(0, last + self.delay - time.time()))
            finally:
                self.wait_seconds += time.monotonic() - waiting
            self.request_count += 1
            requesting = time.monotonic()
            try:
                if self.fetcher:
                    body = self.fetcher(url)
                else:
                    with self.opener.open(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=self.timeout) as r:
                        body = r.read(4_000_001)
                        if len(body) > 4_000_000:
                            raise ValueError('幸福里响应超出大小限制')
                        body = body.decode('utf-8')
                if '验证码' in body or '滑块验证' in body or 'captcha' in body.lower() or '访问过于频繁' in body:
                    cooldown = time.time() + 3600
                    raise ValueError('幸福里要求验证，本轮暂停请求')
                self._check_cancel()
                return body
            except HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308, 403, 429}:
                    cooldown = time.time() + 3600
                raise ValueError(f'幸福里请求失败（HTTP {exc.code}）') from None
            finally:
                self.http_seconds += time.monotonic() - requesting
                _atomic_write_json(path, dict(last_request_at=time.time(), cooldown_until=cooldown))
                if cooldown > time.time():
                    self.cooldown_until = dt.datetime.fromtimestamp(cooldown, dt.UTC).isoformat()

    def close(self):
        pass

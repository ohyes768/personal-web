"""Internal browser protocol. No cookies or arbitrary target URLs cross this boundary."""
import json
import re
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class BrowserFetchError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def page_identity(url):
    match = re.fullmatch(r'https://www\.tmsf\.com/newhouse/(?:property_(\d+)_(\d+)_infoUpgrade|presell_(\d+)_(\d+)_(\d+))\.htm', url)
    if not match:
        raise BrowserFetchError('invalid_target', '新房浏览器目标无效')
    site, pid, psite, ppid, presell = match.groups()
    data = dict(siteid=site or psite, propertyid=pid or ppid)
    if presell:
        data['presellid'] = presell
    return data


class BrowserClient:
    def __init__(self, endpoint, *, cancelled=lambda: False):
        self.endpoint = endpoint.rstrip('/')
        self.session_id = uuid.uuid4().hex
        self.cancelled = cancelled
        self.failure = None
        self.used = False

    def _request(self, path, body, timeout):
        request = Request(self.endpoint + path, data=json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
        try:
            response = urlopen(request, timeout=timeout)
        except HTTPError as exc:
            response = exc
        with response:
            packet = json.loads(response.read(3_000_001))
        if packet.get('error'):
            error = packet['error']
            raise BrowserFetchError(error.get('code', 'worker_error'), error.get('message', '新房浏览器请求失败'))
        return packet

    def fetch_text(self, url, timeout):
        if self.cancelled():
            raise InterruptedError('采集已取消')
        if self.failure:
            raise BrowserFetchError('paused', f'本轮新房详情已暂停：{self.failure}')
        target = page_identity(url)
        try:
            self.used = True
            packet = self._request('/page', {**target, 'session_id': self.session_id}, 60)
            if self.cancelled():
                raise InterruptedError('采集已取消')
            if packet.get('url') != url:
                raise BrowserFetchError('identity_mismatch', '新房浏览器返回页面身份不一致')
            html = packet.get('html')
            if not isinstance(html, str) or not html or len(html.encode()) > 2_000_000:
                raise BrowserFetchError('invalid_response', '新房浏览器未返回有效正文')
            return html
        except InterruptedError:
            raise
        except BrowserFetchError as exc:
            self.failure = exc
            raise
        except Exception as exc:
            self.failure = BrowserFetchError('browser_unavailable', '新房浏览器不可用，本轮暂停新房详情，请检查服务后重试')
            raise self.failure from exc

    def close(self):
        if self.used:
            try:
                self._request('/close', {'session_id': self.session_id}, 3)
            except Exception:
                pass  # Worker also reaps abandoned sessions after its idle timeout.
        self.used = False

"""Single-owner Playwright worker. Run separately: python -m src.browser_worker.

The HTTP loop and Playwright share one thread. API requests cannot interleave browser
operations; health checks may wait at most one bounded navigation. No business data
or browser profiles are mounted in this service.
"""
import json
import logging
import os
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)
IDLE_SECONDS = 120
COOLDOWN_SECONDS = 900
MIN_INTERVAL_SECONDS = 3


class WorkerError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def target_url(payload):
    if set(payload) - {'session_id', 'siteid', 'propertyid', 'presellid'}:
        raise WorkerError('invalid_target', '新房浏览器参数无效')
    if not re.fullmatch(r'[a-f0-9]{32}', str(payload.get('session_id', ''))):
        raise WorkerError('invalid_session', '新房浏览器会话无效')
    for key in ('siteid', 'propertyid', 'presellid'):
        if key == 'presellid' and key not in payload:
            continue
        if not isinstance(payload.get(key), str) or not re.fullmatch(r'\d{1,20}', payload[key]):
            raise WorkerError('invalid_target', '新房浏览器项目编号无效')
    site, pid = payload['siteid'], payload['propertyid']
    if 'presellid' in payload:
        return f'https://www.tmsf.com/newhouse/presell_{site}_{pid}_{payload["presellid"]}.htm'
    return f'https://www.tmsf.com/newhouse/property_{site}_{pid}_infoUpgrade.htm'


class PlaywrightSession:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self.runtime = sync_playwright().start()
        self.browser = None
        try:
            options = dict(headless=True, timeout=15000)
            if os.getenv('TMSF_BROWSER_EXECUTABLE'):
                options['executable_path'] = os.environ['TMSF_BROWSER_EXECUTABLE']
            self.browser = self.runtime.chromium.launch(**options)
            self.context = self.browser.new_context(locale='zh-CN', timezone_id='Asia/Shanghai')
            self.page = self.context.new_page()
        except Exception:
            self.close()
            raise

    def close(self):
        try:
            if self.browser:
                self.browser.close()
        finally:
            self.runtime.stop()


class PageWorker:
    def __init__(self, *, session_factory=PlaywrightSession, clock=time.monotonic, sleeper=time.sleep):
        self.session_factory = session_factory
        self.clock, self.sleeper = clock, sleeper
        self.session = None
        self.session_id = None
        self.last_used = 0
        self.last_navigation = 0
        self.paused_until = 0

    def close(self, session_id=None):
        if session_id is not None and self.session_id != session_id:
            return
        session, self.session = self.session, None
        self.session_id = None
        if session:
            try:
                session.close()
            except Exception:
                logger.exception('Browser session cleanup failed')

    def expire(self):
        if self.session and self.clock() - self.last_used >= IDLE_SECONDS:
            self.close()

    def _navigate(self, url):
        page = self.session.page
        # Third-party scripts can delay DOMContentLoaded after our facts arrive.
        # Wait for the response, then inspect the required content ourselves.
        page.goto(url, wait_until='commit', timeout=25000)
        selector = '#locatedrr' if '/presell_' in url else '.house_float_name_title'
        deadline = self.clock() + 10
        while self.clock() < deadline:
            # Ignore hidden captcha widgets loaded as part of the normal site shell.
            if page.locator('.captcha:visible, .captcha_cover:visible, #nc_1_wrapper:visible').count():
                raise WorkerError('manual_verification', '透明售房网需要人工验证，已暂停新房采集，保留已有资料')
            # Read readiness and HTML in one browser execution. A count() followed
            # by text_content() can wait 30s if the site replaces that node in between.
            snapshot = page.evaluate('''({selector, presell}) => {
                const text = s => document.querySelector(s)?.textContent?.trim() || '';
                const ready = Boolean(text(selector) && (presell ||
                    text('.house_float_name_tips_grey, .house_information_price_residence')));
                return {url: location.href, ready,
                    html: ready ? document.documentElement.outerHTML : null};
            }''', dict(selector=selector, presell='/presell_' in url))
            if snapshot['url'] != url:
                raise WorkerError('identity_mismatch', '新房页面跳转后身份不一致')
            if snapshot['ready']:
                html = snapshot['html']
                if len(html.encode()) > 2_000_000:
                    raise WorkerError('invalid_response', '新房页面过大，未采用资料')
                return html
            page.wait_for_timeout(250)
        raise WorkerError('browser_timeout', '本项目新房页面关键正文加载超时，可稍后重试')

    def fetch(self, payload):
        url = target_url(payload)
        self.expire()
        if self.clock() < self.paused_until:
            raise WorkerError('paused', '新房浏览器验证暂停中，请稍后重试，已有资料保留')
        if self.session_id and self.session_id != payload['session_id']:
            raise WorkerError('busy', '新房浏览器正在处理其他采集，请稍后重试')
        try:
            if not self.session:
                self.session = self.session_factory()
                self.session_id = payload['session_id']
            delay = MIN_INTERVAL_SECONDS - (self.clock() - self.last_navigation)
            if delay > 0:
                self.sleeper(delay)
            self.last_navigation = self.clock()
            html = self._navigate(url)
            self.last_used = self.clock()
            return {'url': url, 'html': html}
        except WorkerError as exc:
            if exc.code in {'manual_verification', 'challenge'}:
                self.paused_until = self.clock() + COOLDOWN_SECONDS
            self.close()
            raise
        except Exception as exc:
            logger.exception('TMSF browser request failed for project %s', payload['propertyid'])
            self.close()
            # Playwright is an optional worker-only dependency; its TimeoutError
            # shares the standard name but does not inherit built-in TimeoutError.
            if isinstance(exc, TimeoutError) or type(exc).__name__ == 'TimeoutError':
                raise WorkerError('browser_timeout', '本项目新房页面加载超时，可稍后重试') from exc
            raise WorkerError('browser_error', '新房浏览器读取失败，本轮暂停，请检查服务后重试') from exc


class WorkerServer(HTTPServer):
    def __init__(self, address, engine):
        self.engine = engine
        super().__init__(address, Handler)

    def service_actions(self):
        self.engine.expire()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def respond(self, status, packet):
        data = json.dumps(packet, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # A local health probe may expire during a bounded navigation.
            pass

    def do_GET(self):
        if self.path != '/health':
            self.respond(404, {})
            return
        self.respond(200, {'ready': True, 'session_active': self.server.engine.session is not None})

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise WorkerError('invalid_request', '请求长度无效')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise WorkerError('invalid_request', '请求格式无效')
            if self.path == '/page':
                result = self.server.engine.fetch(payload)
            elif self.path == '/close':
                sid = payload.get('session_id')
                if not isinstance(sid, str) or not re.fullmatch('[a-f0-9]{32}', sid):
                    raise WorkerError('invalid_session', '新房浏览器会话无效')
                self.server.engine.close(sid)
                result = {'closed': True}
            else:
                self.respond(404, {})
                return
            self.respond(200, result)
        except WorkerError as exc:
            self.respond(409, {'error': {'code': exc.code, 'message': str(exc)}})
        except (ValueError, TimeoutError):
            self.respond(400, {'error': {'code': 'invalid_request', 'message': '新房浏览器请求格式无效'}})

    def log_message(self, fmt, *args):
        logger.info(fmt, *args)


def main():
    logging.basicConfig(level=logging.INFO)
    engine = PageWorker()
    with WorkerServer(('0.0.0.0', int(os.getenv('TMSF_BROWSER_PORT', '8097'))), engine) as server:
        try:
            server.serve_forever(poll_interval=1)
        finally:
            engine.close()


if __name__ == '__main__':
    main()

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from src.services.tmsf_fetcher import TmsfClient

URL = 'https://www.tmsf.com/newhouse/property_33_2946115152_infoUpgrade.htm'


@pytest.fixture
def endpoint():
    requests = []
    reply = {'html': '<html>楼盘正文</html>', 'url': URL}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *_): pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', requests, reply
    server.shutdown()
    server.server_close()
    thread.join()


def test_tmsf_client_reuses_browser_session_and_releases_it(endpoint, monkeypatch):
    url, requests, _ = endpoint
    monkeypatch.setenv('HOUSING_TMSF_BROWSER_URL', url)
    client = TmsfClient()
    assert client.fetch_project_text(URL, 15) == '<html>楼盘正文</html>'
    assert client.fetch_project_text(URL, 15) == '<html>楼盘正文</html>'
    client.close()
    assert [p for p, _ in requests] == ['/page', '/page', '/close']
    assert requests[0][1]['session_id'] == requests[1][1]['session_id']


def test_pause_stops_following_requests_without_losing_cause(endpoint, monkeypatch):
    url, requests, reply = endpoint
    monkeypatch.setenv('HOUSING_TMSF_BROWSER_URL', url)
    reply.update(error={'code': 'manual_verification', 'message': '需要人工验证，暂停新房采集'})
    client = TmsfClient()
    for _ in range(3):
        with pytest.raises(ValueError, match='人工验证'):
            client.fetch_project_text(URL, 15)
    assert len(requests) == 1
    client.close()


def test_browser_rejects_unexpected_final_identity(endpoint, monkeypatch):
    url, _, reply = endpoint
    monkeypatch.setenv('HOUSING_TMSF_BROWSER_URL', url)
    reply['url'] = URL.replace('2946115152', '999')
    client = TmsfClient()
    with pytest.raises(ValueError, match='身份'):
        client.fetch_project_text(URL, 15)
    client.close()


def test_cancelled_request_never_returns_page(endpoint, monkeypatch):
    url, requests, _ = endpoint
    monkeypatch.setenv('HOUSING_TMSF_BROWSER_URL', url)
    client = TmsfClient(cancelled=lambda: True)
    with pytest.raises(InterruptedError):
        client.fetch_project_text(URL, 15)
    assert requests == []
    client.close()


def test_disabled_browser_keeps_injected_http_client(monkeypatch):
    monkeypatch.delenv('HOUSING_TMSF_BROWSER_URL', raising=False)
    client = TmsfClient()
    client.fetch_text = lambda *_: 'legacy HTTP'
    assert client.fetch_project_text(URL, 15) == 'legacy HTTP'
    client.close()


def worker():
    from src.browser_worker import PageWorker
    sessions = []
    def launch():
        session = SimpleNamespace(close=lambda: sessions.append('closed'))
        sessions.append(session)
        return session
    engine = PageWorker(session_factory=launch, sleeper=lambda _: None)
    engine._navigate = lambda url: '<html>rendered</html>'
    return engine, sessions


def payload(sid='a' * 32, **extra):
    return dict(session_id=sid, siteid='33', propertyid='2946115152', **extra)


def test_worker_session_is_exclusive_reused_and_idle_reaped():
    engine, sessions = worker()
    assert engine.fetch(payload())['url'] == URL
    engine.fetch(payload())
    assert len(sessions) == 1
    with pytest.raises(ValueError, match='其他采集'):
        engine.fetch(payload('b' * 32))
    engine.clock = lambda: engine.last_used + 121
    engine.expire()
    assert sessions[-1] == 'closed' and engine.session_id is None


@pytest.mark.parametrize('bad', [payload(site='https://evil.example'),
    {**payload(), 'propertyid': '../esf/1'}, {**payload(), 'siteid': True},
    {**payload(), 'presellid': '123?next=https://evil.example'}, payload('not-a-session')])
def test_worker_rejects_invalid_targets_before_launch(bad):
    engine, sessions = worker()
    with pytest.raises(ValueError):
        engine.fetch(bad)
    assert sessions == []


def test_worker_captcha_closes_browser_and_cools_down_across_sessions():
    from src.browser_worker import WorkerError
    engine, sessions = worker()
    def challenge(_): raise WorkerError('manual_verification', '人工验证')
    engine._navigate = challenge
    with pytest.raises(ValueError): engine.fetch(payload())
    assert sessions[-1] == 'closed'
    with pytest.raises(ValueError, match='暂停'):
        engine.fetch(payload('b' * 32))
    assert len(sessions) == 2


@pytest.mark.parametrize('code,failed,deferred', [('manual_verification', 1, 2), ('paused', 0, 3),
    ('browser_error', 1, 2), ('browser_unavailable', 1, 2), ('busy', 0, 3)])
def test_batch_pause_keeps_names_and_counts_unrequested_projects_as_deferred(endpoint, monkeypatch, tmp_path, code, failed, deferred):
    from scripts import fetch_tmsf_binjiang_communities as listing
    from src.services import directory_collection
    from src.services.community_registry import CommunityRegistry
    url, requests, reply = endpoint
    monkeypatch.setenv('HOUSING_TMSF_BROWSER_URL', url)
    reply.update(error={'code': code, 'message': '新房请求暂停'})
    monkeypatch.setattr(listing, 'fetch_binjiang_communities', lambda: [])
    monkeypatch.setattr(directory_collection, 'pause', lambda _: None)
    projects = [dict(siteid=33, propertyid=100+i, propertyname=f'测试园{i}',
                     districtname='滨江', propertystateid=2) for i in range(3)]
    monkeypatch.setattr(TmsfClient, 'fetch_text', lambda *_: 'var data_auto = ' + json.dumps(projects))
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    report = directory_collection.collect_names(store, ['tmsf'])
    assert report['new'] == 3 and len(store.sources()) == 3
    assert report['property_types_failed'] == failed
    assert report['property_types_deferred'] == deferred
    assert len(report['errors']) == failed
    assert report['phase'] == 'partial_failed'
    assert str(deferred) in report['truncated'][0]['message']
    assert [p for p, _ in requests] == ['/page', '/close']
    summary = report['truncated'][0]['message']
    if code in {'manual_verification', 'paused'}:
        assert '验证冷却' in summary
    else:
        assert '冷却' not in summary
    if code == 'browser_timeout':
        assert '超时' in summary
    if code in {'browser_error', 'browser_unavailable'}:
        assert '服务' in summary
    if code == 'busy':
        assert '占用' in summary


class FakePage:
    def __init__(self, *, captcha=False, ready=True):
        self.url = URL
        self.captcha = captcha
        self.ready = ready
        self.navigations = []
        self.waits = 0

    def goto(self, url, **options):
        self.url = url
        self.navigations.append(options)

    def locator(self, selector):
        visible = self.captcha if ':visible' in selector else self.ready
        return SimpleNamespace(count=lambda: int(visible), first=SimpleNamespace(
            count=lambda: int(visible), text_content=lambda: '住宅正文' if visible else ''))

    def content(self):
        return '<html>住宅正文</html>'

    def evaluate(self, _, options):
        return dict(url=self.url, ready=self.ready,
                    html=self.content() if self.ready else None)

    def wait_for_timeout(self, _):
        self.waits += 1


def navigation_worker(page):
    from src.browser_worker import PageWorker
    engine = PageWorker(clock=lambda: page.waits * .25, sleeper=lambda _: None)
    engine.session = SimpleNamespace(page=page, close=lambda: None)
    return engine


def test_navigation_uses_key_content_without_waiting_for_external_scripts():
    page = FakePage()
    engine = navigation_worker(page)
    assert engine._navigate(URL) == '<html>住宅正文</html>'
    assert page.navigations == [dict(wait_until='commit', timeout=25000)]


def test_dynamic_node_replacement_does_not_start_locator_auto_wait():
    page = FakePage()
    original_locator = page.locator
    def disappears():
        raise TimeoutError('node disappeared after count; locator waited 30 seconds')
    def locator(selector):
        if ':visible' in selector:
            return original_locator(selector)
        return SimpleNamespace(first=SimpleNamespace(count=lambda: 1, text_content=disappears))
    page.locator = locator
    engine = navigation_worker(page)
    assert engine._navigate(URL) == '<html>住宅正文</html>'
    assert page.waits == 0


def test_incomplete_snapshot_is_polled_until_facts_arrive():
    page = FakePage(ready=False)
    original_evaluate = page.evaluate
    def evaluate(script, options):
        page.ready = page.waits >= 2
        return original_evaluate(script, options)
    page.evaluate = evaluate
    engine = navigation_worker(page)
    assert engine._navigate(URL) == '<html>住宅正文</html>'
    assert page.waits == 2


def test_missing_content_is_timeout_without_verification_cooldown():
    page = FakePage(ready=False)
    engine = navigation_worker(page)
    with pytest.raises(ValueError) as failure:
        engine.fetch(payload())
    assert failure.value.code == 'browser_timeout'
    assert engine.paused_until == 0


@pytest.mark.parametrize('timeout_type', [TimeoutError, type('TimeoutError', (Exception,), {})])
def test_transport_timeout_reports_specific_error_and_logs_cause(caplog, timeout_type):
    engine, _ = worker()
    def timeout(_):
        raise timeout_type('Page.goto timed out')
    engine._navigate = timeout
    with pytest.raises(ValueError) as failure:
        engine.fetch(payload())
    assert failure.value.code == 'browser_timeout'
    assert engine.paused_until == 0
    assert any(record.exc_info for record in caplog.records)


def test_visible_captcha_still_prevents_content_and_starts_cooldown():
    engine = navigation_worker(FakePage(captcha=True))
    with pytest.raises(ValueError) as failure:
        engine.fetch(payload())
    assert failure.value.code == 'manual_verification'
    assert engine.paused_until == 900


def test_redirected_content_cannot_be_returned_as_target_project():
    page = FakePage()
    def redirect(url, **_):
        page.url = url.replace('2946115152', '999')
    page.goto = redirect
    engine = navigation_worker(page)
    with pytest.raises(ValueError) as failure:
        engine.fetch(payload())
    assert failure.value.code == 'identity_mismatch'
    assert engine.paused_until == 0


def test_health_probe_disconnect_does_not_raise():
    from src.browser_worker import Handler
    def disconnected(_):
        raise BrokenPipeError()
    handler = SimpleNamespace(send_response=lambda _: None, send_header=lambda *_: None,
        end_headers=lambda: None, wfile=SimpleNamespace(write=disconnected))
    Handler.respond(handler, 200, {'ready': True})


def timeout_client(outcomes):
    from src.services.tmsf_browser import BrowserClient, BrowserFetchError
    calls = []
    client = BrowserClient('http://worker')
    def request(path, body, timeout):
        calls.append(body)
        outcome = outcomes.pop(0)
        if outcome:
            raise BrowserFetchError(outcome, '本项目加载失败')
        url = f'https://www.tmsf.com/newhouse/property_{body["siteid"]}_{body["propertyid"]}_infoUpgrade.htm'
        return dict(url=url, html='<html>正文</html>')
    client._request = request
    return client, calls


def test_one_project_timeout_does_not_block_next_project():
    client, calls = timeout_client(['browser_timeout', None])
    with pytest.raises(ValueError) as failure:
        client.fetch_text(URL, 15)
    assert not failure.value.task_paused
    assert client.fetch_text(URL.replace('2946115152', '999'), 15) == '<html>正文</html>'
    assert len(calls) == 2 and client.failure is None


def test_three_consecutive_timeouts_stop_further_requests():
    client, calls = timeout_client(['browser_timeout'] * 3)
    for index in range(3):
        with pytest.raises(ValueError) as failure:
            client.fetch_text(URL.replace('2946115152', str(index + 1)), 15)
        assert failure.value.task_paused == (index == 2)
    with pytest.raises(ValueError) as failure:
        client.fetch_text(URL, 15)
    assert failure.value.code == 'paused' and len(calls) == 3


def test_success_resets_consecutive_timeout_budget():
    client, calls = timeout_client(['browser_timeout', 'browser_timeout', None, 'browser_timeout'])
    for index in range(4):
        if index == 2:
            client.fetch_text(URL, 15)
        else:
            with pytest.raises(ValueError): client.fetch_text(URL, 15)
    assert client.failure is None and len(calls) == 4


def test_verification_after_timeout_still_stops_immediately():
    client, calls = timeout_client(['browser_timeout', 'manual_verification'])
    for _ in range(3):
        with pytest.raises(ValueError): client.fetch_text(URL, 15)
    assert len(calls) == 2 and client.failure.code == 'manual_verification'


@pytest.mark.parametrize('outcomes,succeeded,failed,deferred,reason', [
    (['browser_timeout', None, None, None, None], 4, 1, 0, None),
    (['browser_timeout'] * 3, 0, 3, 2, 'browser_timeout'),
    (['browser_timeout', 'manual_verification'], 0, 2, 3, 'manual_verification'),
])
def test_batch_isolated_timeouts_continue_but_real_pause_keeps_correct_reason(
        monkeypatch, tmp_path, outcomes, succeeded, failed, deferred, reason):
    from scripts import fetch_tmsf_binjiang_communities as listing
    from src.services import directory_collection
    from src.services.community_registry import CommunityRegistry
    from src.services.tmsf_browser import BrowserClient, BrowserFetchError
    outcomes = list(outcomes)
    calls = []
    def request(self, path, body, timeout):
        if path == '/close': return {}
        calls.append(body['propertyid'])
        outcome = outcomes.pop(0)
        if outcome: raise BrowserFetchError(outcome, outcome)
        pid = body['propertyid']
        url = f'https://www.tmsf.com/newhouse/property_33_{pid}_infoUpgrade.htm'
        html = (f'<div class="house_float_name_title">测试园{pid}</div>'
                '<a id="districtname">滨江楼盘</a>'
                '<div class="house_float_name_tips_grey">住宅</div>'
                '<div>楼盘地址</div><div>滨江区浦沿路100号</div>')
        return dict(url=url, html=html)
    monkeypatch.setattr(BrowserClient, '_request', request)
    monkeypatch.setenv('HOUSING_TMSF_BROWSER_URL', 'http://worker')
    monkeypatch.setattr(listing, 'fetch_binjiang_communities', lambda: [])
    monkeypatch.setattr(directory_collection, 'pause', lambda _: None)
    projects = [dict(siteid=33, propertyid=i, propertyname=f'测试园{i}',
                     districtname='滨江', propertystateid=2) for i in range(100, 105)]
    monkeypatch.setattr(TmsfClient, 'fetch_text', lambda *_: 'var data_auto = ' + json.dumps(projects))
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    report = directory_collection.collect_names(store, ['tmsf'])
    assert len(store.sources()) == 5
    assert (report['property_types'], report['property_types_failed'], report['property_types_deferred']) == (succeeded, failed, deferred)
    assert len(calls) == succeeded + failed
    assert report.get('newhouse_pause_reason') == reason
    assert len(report['truncated']) == bool(deferred)
    if reason == 'manual_verification': assert '验证冷却' in report['truncated'][0]['message']

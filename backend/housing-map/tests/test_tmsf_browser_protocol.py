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


@pytest.mark.parametrize('code,failed,deferred', [('manual_verification', 1, 2), ('paused', 0, 3)])
def test_batch_pause_keeps_names_and_counts_unrequested_projects_as_deferred(endpoint, monkeypatch, tmp_path, code, failed, deferred):
    from scripts import fetch_tmsf_binjiang_communities as listing
    from src.services import directory_collection
    from src.services.community_registry import CommunityRegistry
    url, requests, reply = endpoint
    monkeypatch.setenv('HOUSING_TMSF_BROWSER_URL', url)
    reply.update(error={'code': code, 'message': '需要人工验证，暂停新房采集'})
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

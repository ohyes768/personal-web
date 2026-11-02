import pytest
from src.services import amap_directory as amap
from src.services.directory_use_review import _search_review


@pytest.fixture
def transport(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(amap.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(amap.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(amap, '_NEXT_REQUEST_AT', 0.0)
    monkeypatch.setenv('AMAP_WEB_SERVICE_KEY', 'private-key')
    clients = []
    def create(responses):
        client = amap.AmapClient()
        clients.append(client)
        results, calls = iter(responses), []
        class Response:
            def __init__(self, data):
                self.data = data
                self.status_code = 429 if data == 429 else 200
            def raise_for_status(self): pass
            def json(self): return self.data
        def get(url, params, **kwargs):
            calls.append((clock[0], dict(params)))
            return Response(next(results))
        monkeypatch.setattr(client.session, 'get', get)
        return client, calls
    yield create
    for client in clients: client.close()


def ok(sid='1', count='1'):
    return {'status': '1', 'count': count, 'pois': [{'id': sid}]}


def test_shared_spacing_across_clients_pages_and_aliases(transport):
    a, calls = transport([ok(), ok()])
    b, other = transport([ok()])
    a.search_name('国信嘉园', '滨江')
    a.search_name('国信嘉园', '滨江', page=2)
    b.search_name('国信嘉园(排屋)', '滨江')
    assert [c[0] for c in calls + other] == [0, 2, 4]
    assert calls[1][1]['page'] == 2


@pytest.mark.parametrize('code', ['10014', '10015', '10019', '10020', '10021', '10029', 429])
def test_backoff_retries_same_page_and_parameters(transport, code):
    limited = 429 if code == 429 else {'status': '0', 'infocode': code}
    client, calls = transport([limited, limited, limited, ok()])
    assert client.search_name('国信嘉园', '滨江', types=None, page=4) == ([{'id': '1'}], 1)
    assert [c[0] for c in calls] == [0, 2, 6, 14]
    assert all(c[1] == calls[0][1] for c in calls)
    assert calls[0][1]['page'] == 4


def test_exhausted_retries_bounded_with_shared_cooldown(transport):
    a, calls = transport([{'status': '0', 'infocode': '10021'}] * 4)
    b, other = transport([ok()])
    with pytest.raises(ValueError, match='10021'):
        a.search_name('国信嘉园', '滨江')
    b.search_name('其他小区', '滨江')
    assert len(calls) == 4
    assert other[0][0] == 22


@pytest.mark.parametrize('code', ['10001', '10003', '10044', '40000', 'key=private-key'])
def test_permanent_error_not_retried_and_redacted(transport, code):
    client, calls = transport([{'status': '0', 'infocode': code, 'info': 'key=private-key'}])
    with pytest.raises(ValueError) as exc:
        client.search_name('国信嘉园', '滨江')
    assert len(calls) == 1
    assert 'private-key' not in str(exc.value)
    if code.isdigit(): assert code in str(exc.value)


def test_pagination_recovers_fourth_page_without_losing_previous_pages(transport):
    pages = [ok(str(i), '4') for i in range(4)]
    client, calls = transport([*pages[:3], {'status': '0', 'infocode': '10021'}, pages[3]])
    rows, complete = _search_review(client, '国信嘉园', '滨江', cancelled=lambda: False)
    assert complete and rows == [{'id': str(i)} for i in range(4)]
    assert [c[1]['page'] for c in calls] == [1, 2, 3, 4, 4]
    assert [c[0] for c in calls] == [0, 2, 4, 6, 8]


def test_simultaneous_clients_share_gate(transport):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    a, calls = transport([ok()])
    b, other = transport([ok()])
    start = threading.Barrier(2)
    def query(client):
        start.wait(timeout=5)
        return client.search_name('国信嘉园', '滨江')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(query, client) for client in (a, b)]
        assert all(f.result(timeout=5)[1] == 1 for f in futures)
    assert sorted(c[0] for c in calls + other) == [0, 2]


@pytest.mark.parametrize('data', [None, [], {'status': '1', 'count': 'bad', 'pois': []}])
def test_malformed_response_is_safe_and_not_retried(transport, data):
    client, calls = transport([data])
    with pytest.raises(ValueError, match='高德位置补全'):
        client.search_name('国信嘉园', '滨江')
    assert len(calls) == 1


def test_explicit_budget_counts_retries_and_stops_before_extra_http(transport):
    import threading
    from src.services.collection_pipeline import RequestBudgetClient, RequestBudgetExhausted
    client, calls = transport([{'status': '0', 'infocode': '10021'}] * 4)
    budget = RequestBudgetClient(lambda: client, limit=2, delay=0, cancel=threading.Event())
    with pytest.raises(RequestBudgetExhausted):
        budget.search_name('国信嘉园', '滨江')
    assert budget.used == len(calls) == 2


def test_cancel_during_backoff_prevents_retry_http(transport, monkeypatch):
    import threading
    from src.services.collection_pipeline import RequestBudgetClient
    cancel = threading.Event()
    client, calls = transport([{'status': '0', 'infocode': '10021'}, ok()])
    original_sleep = amap.time.sleep
    def stop(seconds):
        original_sleep(seconds)
        cancel.set()
    monkeypatch.setattr(amap.time, 'sleep', stop)
    budget = RequestBudgetClient(lambda: client, limit=None, delay=0, cancel=cancel)
    with pytest.raises(InterruptedError):
        budget.search_name('国信嘉园', '滨江')
    assert budget.used == len(calls) == 1

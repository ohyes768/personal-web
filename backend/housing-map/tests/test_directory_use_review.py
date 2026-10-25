import json

import pytest

from src.services.community_registry import CommunityRegistry, dump
from src.services.directory_policy import KEY, VERSION
from src.services.directory_use_review import UseReviewOutcome, review_one
from src.services.use_review_policy import use_identity, use_review_view


def poi(sid='B1', name='风雅钱塘', typecode='120302', type_text='住宅小区'):
    return dict(id=sid, name=name, adname='滨江区', address='月明路1076号',
                typecode=typecode, type=type_text, location='120.20749,30.20226')


class Client:
    def __init__(self, rows=None, error=None, callback=None, count=None, by_name=None):
        self.rows = [poi()] if rows is None else rows
        self.error, self.callback = error, callback
        self.count, self.by_name = count, by_name or {}
        self.calls = 0
        self.queries = []
        self.types = []

    def search_name(self, name, district, types='120300|120203', *, page=1):
        self.calls += 1
        self.queries.append(name)
        self.types.append(types)
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        rows = self.by_name.get(name, self.rows)
        return rows, self.count if self.count is not None else len(rows)

    def close(self):
        pass


@pytest.fixture
def setup(tmp_path):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    c = store.create('风雅钱塘', district='滨江', address='月明路1076号')
    s = store.ingest(dict(source='tmsf', source_id='t1', name='风雅钱塘', district='滨江',
                          address='月明路1076号', property_type='商贸', listing_count=3,
                          market_state='second_hand'))
    store.associate(s['id'], c['community_id'])
    with store.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    return store, c['community_id'], tmp_path


def saved_review(store, cid):
    with store.db() as db:
        row = db.execute('SELECT payload FROM communities WHERE id=?', (cid,)).fetchone()
        return json.loads(row[0]).get('use_review')


def update_master(store, cid, **values):
    with store.db() as db:
        row = db.execute('SELECT payload FROM communities WHERE id=?', (cid,)).fetchone()
        payload = json.loads(row[0]); payload.update(values)
        db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), cid))


def test_review_stores_residential_evidence_for_a_named_match(setup):
    store, cid, data = setup
    assert review_one(store, data, cid, Client()) == 'updated'
    saved = saved_review(store, cid)
    assert saved['state'] == 'checked'
    assert saved['category'] == 'residential'
    assert saved['rule_version'] == 'use-review-v1'
    assert saved['evidence']['poi_id'] == 'B1'
    assert saved['evidence']['typecode'] == '120302'
    assert saved['evidence']['matched_by'] == 'exact'
    assert saved['checked_at'] and saved['identity']


def test_review_stores_non_residential_evidence(setup):
    store, cid, data = setup
    review_one(store, data, cid, Client([poi(typecode='120101', type_text='写字楼')]))
    saved = saved_review(store, cid)
    assert saved['state'] == 'checked' and saved['category'] == 'non_residential'


def test_review_queries_without_a_category_filter(setup):
    store, cid, data = setup
    client = Client()
    review_one(store, data, cid, client)
    assert client.types == [None]


def test_review_persists_not_found(setup):
    store, cid, data = setup
    with pytest.raises(UseReviewOutcome) as exc:
        review_one(store, data, cid, Client([]))
    assert exc.value.state == 'not_found'
    saved = saved_review(store, cid)
    assert saved['state'] == 'not_found' and saved['category'] is None and saved['evidence'] is None


def test_review_persists_a_transport_error(setup):
    store, cid, data = setup
    with pytest.raises(UseReviewOutcome) as exc:
        review_one(store, data, cid, Client(error=RuntimeError('boom')))
    assert exc.value.state == 'error'
    saved = saved_review(store, cid)
    assert saved['state'] == 'error' and 'boom' not in (saved['error'] or '')


def test_review_marks_a_truncated_result_uncertain(setup):
    store, cid, data = setup
    with pytest.raises(UseReviewOutcome) as exc:
        review_one(store, data, cid, Client(count=40))
    assert exc.value.state == 'uncertain'
    saved = saved_review(store, cid)
    assert saved['state'] == 'uncertain' and saved['category'] is None


@pytest.fixture
def paged_client(monkeypatch):
    from src.services.amap_directory import AmapClient
    monkeypatch.setenv('AMAP_WEB_SERVICE_KEY', 'test-key')
    clients = []

    def make(pages, count, *, callback=None):
        client = AmapClient()
        clients.append(client)
        calls = []

        def get(url, params, **kwargs):
            page = params['page']
            calls.append(dict(params))
            if callback:
                callback(page)
            rows = pages[page - 1] if page <= len(pages) else []
            if isinstance(rows, Exception):
                raise rows

            class Response:
                def raise_for_status(self): pass
                def json(self):
                    total = count[page - 1] if isinstance(count, list) else count
                    return {'status': '1', 'count': str(total), 'pois': rows}

            return Response()

        monkeypatch.setattr(client.session, 'get', get)
        return client, calls

    yield make
    for client in clients:
        client.close()


def unrelated(start, stop):
    return [poi(sid=str(i), name=f'无关商店{i}') for i in range(start, stop)]


def test_review_finds_the_match_after_the_first_page(setup, paged_client):
    store, cid, data = setup
    client, calls = paged_client([unrelated(0, 25), unrelated(25, 50),
                                 unrelated(50, 59) + [poi()]], 60)
    assert review_one(store, data, cid, client) == 'updated'
    assert saved_review(store, cid)['evidence']['poi_id'] == 'B1'
    assert [c['page'] for c in calls] == [1, 2, 3]
    assert all(c['city'] == '330108' and 'types' not in c for c in calls)


def test_review_checks_later_pages_for_conflicting_categories(setup, paged_client):
    store, cid, data = setup
    client, calls = paged_client([[poi()] + unrelated(0, 24),
                                 [poi(sid='B2', typecode='120101')]], 26)
    with pytest.raises(UseReviewOutcome) as exc:
        review_one(store, data, cid, client)
    assert exc.value.state == 'uncertain'
    assert saved_review(store, cid)['candidates_count'] == 2
    assert len(calls) == 2


@pytest.mark.parametrize('kind', ['empty', 'duplicate', 'overlap', 'cap', 'changed_count'])
def test_incomplete_paging_never_publishes_evidence(setup, paged_client, kind):
    store, cid, data = setup
    first = [poi()] + unrelated(0, 24)
    pages, count = {
        'empty': ([first, []], 26),
        'duplicate': ([first, first], 26),
        # Raw row count reaches 26 but there are only 25 distinct POIs.
        'overlap': ([first, [first[0]], []], 26),
        'cap': ([first] + [unrelated(i * 25, (i + 1) * 25) for i in range(1, 9)], 201),
        'changed_count': ([first, unrelated(24, 26)], [26, 27]),
    }[kind]
    client, calls = paged_client(pages, count)
    with pytest.raises(UseReviewOutcome) as exc:
        review_one(store, data, cid, client)
    assert exc.value.state == 'uncertain'
    assert saved_review(store, cid)['evidence'] is None
    assert len(calls) == (8 if kind == 'cap' else 2)


def test_overlapping_pages_continue_until_unique_poi_count_is_complete(setup, paged_client):
    store, cid, data = setup
    first = unrelated(0, 25)
    client, calls = paged_client([first, first[20:] + unrelated(25, 45),
                                 unrelated(45, 49) + [poi()]], 50)
    assert review_one(store, data, cid, client) == 'updated'
    assert len(calls) == 3
    assert saved_review(store, cid)['state'] == 'checked'


def test_exactly_200_results_can_complete_on_page_eight(setup, paged_client):
    store, cid, data = setup
    pages = [unrelated(i * 25, (i + 1) * 25) for i in range(8)]
    pages[-1][-1] = poi()
    client, calls = paged_client(pages, 200)
    assert review_one(store, data, cid, client) == 'updated'
    assert len(calls) == 8


def test_alias_search_also_paginates(setup, paged_client):
    store, cid, data = setup
    update_master(store, cid, community_name='风雅钱塘世纪花园', aliases=['风雅钱塘'])
    client, calls = paged_client([unrelated(0, 25), [poi()]], 26)
    original_get = client.session.get

    def get(url, params, **kwargs):
        if params['keywords'] == '风雅钱塘世纪花园':
            class Response:
                def raise_for_status(self): pass
                def json(self): return {'status': '1', 'count': '0', 'pois': []}
            return Response()
        return original_get(url, params, **kwargs)

    client.session.get = get
    assert review_one(store, data, cid, client) == 'updated'
    assert [c['page'] for c in calls] == [1, 2]
    assert all(c['keywords'] == '风雅钱塘' for c in calls)
    assert saved_review(store, cid)['evidence']['matched_by'] == 'alias'


def test_page_failure_does_not_publish_first_page_match(setup, paged_client):
    store, cid, data = setup
    client, calls = paged_client([[poi()] + unrelated(0, 24), RuntimeError('secret')], 26)
    with pytest.raises(UseReviewOutcome) as exc:
        review_one(store, data, cid, client)
    assert exc.value.state == 'error'
    assert saved_review(store, cid)['evidence'] is None
    assert len(calls) == 2


def test_cancel_between_pages_stops_requests_and_publication(setup, paged_client):
    store, cid, data = setup
    cancelled = []
    client, calls = paged_client([[poi()] + unrelated(0, 24)], 26,
                                 callback=lambda page: cancelled.append(True))
    with pytest.raises(InterruptedError):
        review_one(store, data, cid, client, cancelled=lambda: bool(cancelled))
    assert len(calls) == 1
    assert saved_review(store, cid) is None


def test_review_does_not_write_when_cancelled(setup):
    store, cid, data = setup
    with pytest.raises(InterruptedError):
        review_one(store, data, cid, Client(), cancelled=lambda: True)
    assert saved_review(store, cid) is None


def test_review_refuses_to_write_when_the_community_changed(setup):
    store, cid, data = setup
    client = Client(callback=lambda: update_master(store, cid, note='changed during query'))
    with pytest.raises(ValueError, match='已变化'):
        review_one(store, data, cid, client)
    assert saved_review(store, cid) is None


def test_review_skips_an_existing_valid_evidence_unless_forced(setup):
    store, cid, data = setup
    review_one(store, data, cid, Client())
    assert review_one(store, data, cid, Client()) == 'skipped'
    client = Client([poi(typecode='120101', type_text='写字楼')])
    assert review_one(store, data, cid, client, force=True) == 'updated'
    assert saved_review(store, cid)['category'] == 'non_residential'


def test_review_retries_the_alias_when_the_primary_name_finds_nothing(setup):
    store, cid, data = setup
    update_master(store, cid, community_name='风雅钱塘世纪花园', aliases=['风雅钱塘'])
    client = Client(rows=[], by_name={'风雅钱塘': [poi()]})
    assert review_one(store, data, cid, client) == 'updated'
    assert client.queries == ['风雅钱塘世纪花园', '风雅钱塘']
    assert saved_review(store, cid)['evidence']['matched_by'] == 'alias'


def test_identity_change_invalidates_the_stored_evidence(setup):
    store, cid, data = setup
    review_one(store, data, cid, Client())
    with store.db() as db:
        row = db.execute('SELECT payload FROM communities WHERE id=?', (cid,)).fetchone()
        target = json.loads(row[0])
    assert use_review_view(target)['state'] == 'checked'
    target['community_name'] = '风雅钱塘二期'
    assert use_review_view(target)['state'] is None
    assert use_identity(target) != use_identity(json.loads(
        db.execute('SELECT payload FROM communities WHERE id=?', (cid,)).fetchone()[0]))


def test_review_needs_a_tmsf_record(setup):
    store, cid, data = setup
    store.delete(cid)
    with pytest.raises(ValueError):
        review_one(store, data, cid, Client())

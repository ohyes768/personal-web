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

    def search_name(self, name, district, types='120300|120203'):
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

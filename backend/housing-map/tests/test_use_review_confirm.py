import pytest

from src.services.community_registry import CommunityRegistry
from src.services.directory_policy import KEY, VERSION
from src.services.directory_use_review import review_one
from src.services.use_review_policy import contrary_evidence, use_review_view

EVIDENCE = [{'source': 'kerui', 'url': 'https://www.cihud.com/x/1', 'note': '克而瑞：住宅'}]


def poi(sid='B1', name='风雅钱塘', typecode='120302'):
    return dict(id=sid, name=name, adname='滨江区', address='月明路1076号',
                typecode=typecode, type='住宅小区', location='120.20749,30.20226')


class Client:
    def __init__(self, rows=None):
        self.rows = [poi()] if rows is None else rows

    def search_name(self, name, district, types='120300|120203'):
        return self.rows, len(self.rows)

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


def test_confirm_writes_the_decision_and_an_audit_event(setup):
    store, cid, data = setup
    value = store.confirm_use(cid, revision=1, decision='residential',
                              property_type='住宅', use_evidence=EVIDENCE, reason='克而瑞与房天下均为住宅')
    assert value['state'] == 'admitted' and value['decision_kind'] == 'manual'
    assert value['use_rule'] == 'use-review-v1' and value['use_decision'] == 'residential'
    assert value['property_type'] == '住宅'
    assert value['use_evidence'][0]['url'] == 'https://www.cihud.com/x/1'
    assert value['revision'] == 2 and value['decided_at']
    saved = store.admission(cid)
    assert saved['use_decision'] == 'residential'
    assert any(e['action'] == 'admission_use_confirm' for e in store.events(cid))


def test_confirm_non_residential_records_the_reason(setup):
    store, cid, data = setup
    value = store.confirm_use(cid, revision=1, decision='non_residential',
                              use_evidence=EVIDENCE, reason='高德与克而瑞均为写字楼')
    assert value['state'] == 'excluded' and value['property_type'] is None
    assert value['reason'] == '高德与克而瑞均为写字楼'


def test_confirm_requires_evidence_with_a_link(setup):
    store, cid, data = setup
    with pytest.raises(ValueError, match='证据链接'):
        store.confirm_use(cid, revision=1, decision='residential', property_type='住宅')
    with pytest.raises(ValueError, match='证据链接'):
        store.confirm_use(cid, revision=1, decision='residential', property_type='住宅',
                          use_evidence=[{'source': 'amap', 'url': '', 'note': ''}])


def test_confirm_requires_a_reason_for_non_residential(setup):
    store, cid, data = setup
    with pytest.raises(ValueError, match='理由'):
        store.confirm_use(cid, revision=1, decision='non_residential', use_evidence=EVIDENCE)


def test_confirm_requires_a_residential_type(setup):
    store, cid, data = setup
    with pytest.raises(ValueError, match='住宅、别墅或排屋'):
        store.confirm_use(cid, revision=1, decision='residential', use_evidence=EVIDENCE)
    with pytest.raises(ValueError, match='住宅、别墅或排屋'):
        store.confirm_use(cid, revision=1, decision='residential', property_type='写字楼',
                          use_evidence=EVIDENCE)


def test_confirm_rejects_a_stale_revision(setup):
    store, cid, data = setup
    store.confirm_use(cid, revision=1, decision='residential', property_type='住宅', use_evidence=EVIDENCE)
    with pytest.raises(ValueError, match='审核版本已变化'):
        store.confirm_use(cid, revision=1, decision='non_residential', use_evidence=EVIDENCE, reason='改判')


def test_confirm_rejects_a_deleted_target(setup):
    store, cid, data = setup
    store.delete(cid)
    with pytest.raises(ValueError, match='已删除'):
        store.confirm_use(cid, revision=1, decision='residential', property_type='住宅', use_evidence=EVIDENCE)


def test_confirm_cannot_override_a_manual_exclusion(setup):
    store, cid, data = setup
    store.decide_admission(cid, 'exclude', revision=1, reason='人工排除')
    with pytest.raises(ValueError, match='人工排除或审核锁优先'):
        store.confirm_use(cid, revision=2, decision='residential', property_type='住宅', use_evidence=EVIDENCE)
    assert store.admission(cid)['decision_kind'] == 'manual'
    assert store.admission(cid)['state'] == 'excluded'


def test_confirm_requires_the_directory_flow(setup, tmp_path):
    store = CommunityRegistry(tmp_path / 'plain.sqlite3')
    c = store.create('风雅钱塘', district='滨江', address='月明路1076号')
    with pytest.raises(ValueError, match='名单流程迁移'):
        store.confirm_use(c['community_id'], revision=1, decision='residential',
                          property_type='住宅', use_evidence=EVIDENCE)


def test_directory_mode_still_rejects_the_legacy_admit(setup):
    store, cid, data = setup
    with pytest.raises(ValueError, match='不能手工绕过'):
        store.decide_admission(cid, 'admit', revision=1, property_type='住宅')


def test_a_review_refresh_never_overwrites_the_human_decision(setup):
    store, cid, data = setup
    store.confirm_use(cid, revision=1, decision='residential', property_type='住宅', use_evidence=EVIDENCE)
    before = store.admission(cid)
    review_one(store, data, cid, Client())
    assert store.admission(cid) == before


def test_contrary_evidence_is_reported_only_after_the_decision(setup):
    store, cid, data = setup
    admission = store.confirm_use(cid, revision=1, decision='residential',
                                   property_type='住宅', use_evidence=EVIDENCE)
    records = [r for r in store.sources() if r['status'] == 'matched']
    assert contrary_evidence(admission, records, {'state': 'checked', 'category': 'residential',
                                                  'checked_at': '2000-01-01T00:00:00+00:00'}) is None
    assert contrary_evidence(admission, records, {'state': 'checked', 'category': 'non_residential',
                                                  'checked_at': '2999-01-01T00:00:00+00:00'})
    assert contrary_evidence(admission, records, {'state': 'checked', 'category': 'residential',
                                                  'checked_at': '2999-01-01T00:00:00+00:00'}) is None
    fresh = dict(records[0], property_type='商贸', property_type_checked_at='2999-01-01T00:00:00+00:00')
    assert contrary_evidence(admission, [fresh], {'state': None})
    stale = dict(records[0], property_type='商贸', property_type_checked_at='2000-01-01T00:00:00+00:00')
    assert contrary_evidence(admission, [stale], {'state': None}) is None

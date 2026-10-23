"""端到端演练：透明售房网标「商贸」的高德住宅小区，走复核到人工确认后收录。"""
import pytest

from src.services.community_registry import CommunityRegistry
from src.services.directory_policy import KEY, VERSION
from src.services.directory_use_review import UseReviewJob
from src.services.directory_workflow import admitted, inventory


def poi(sid='B1', name='风雅钱塘世纪花园', typecode='120302', type_text='住宅小区'):
    return dict(id=sid, name=name, adname='滨江区', address='月明路1076号',
                typecode=typecode, type=type_text, location='120.20749,30.20226')


class Client:
    def __init__(self, rows=None):
        self.rows = rows

    def search_name(self, name, district, types='120300|120203'):
        rows = self.rows if self.rows is not None else [poi(name=name)]
        return rows, len(rows)

    def close(self):
        pass


@pytest.fixture
def scenario(tmp_path):
    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    with store.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    c = store.create('风雅钱塘世纪花园', district='滨江', address='月明路1076号')
    s = store.ingest(dict(source='tmsf', source_id='10001039', name='风雅钱塘世纪花园', district='滨江',
                          address='月明路1076号', property_type='商贸', listing_count=3,
                          market_state='second_hand'))
    store.associate(s['id'], c['community_id'])
    return store, c['community_id'], tmp_path


def test_a_mislabelled_community_goes_through_review_into_the_catalog(scenario):
    store, cid, data = scenario
    row = next(r for r in inventory(store, data) if r['community_id'] == cid)
    assert row['qualification'] == 'non_residential'
    assert row['admission_state'] == 'excluded'
    assert cid not in {c['community_id'] for c in admitted(store, data)}

    job = UseReviewJob(store)
    job._run(client=Client(), delay=0)
    assert job.snapshot()['conflict'] == 1

    row = next(r for r in inventory(store, data) if r['community_id'] == cid)
    assert row['qualification'] == 'use_conflict'
    assert row['facts_state'] == 'incomplete'
    assert row['admission_state'] == 'excluded'
    assert row['use_review']['result'] == 'conflict'
    assert row['use_review']['evidence']['type_text'] == '住宅小区'
    assert cid not in {c['community_id'] for c in admitted(store, data)}

    store.confirm_use(cid, revision=store.admission(cid)['revision'], decision='residential',
                      property_type='住宅',
                      use_evidence=[{'source': 'kerui', 'url': 'https://www.cihud.com/x/1', 'note': '克而瑞：住宅'}],
                      reason='克而瑞、房天下与高德三方一致为住宅')

    row = next(r for r in inventory(store, data) if r['community_id'] == cid)
    assert row['qualification'] == 'eligible'
    assert row['admission_state'] == 'admitted'
    assert row['effective_property_type'] == '住宅'
    assert row['use_review']['human']['decision'] == 'residential'
    assert row['use_review']['re_review'] is False
    assert cid in {c['community_id'] for c in admitted(store, data)}
    # 收录后即进入租金与法拍的住宅目标集合。
    assert any(c['community_id'] == cid for c in admitted(store, data))


def test_a_review_does_not_change_the_verdict_without_a_human_decision(scenario):
    store, cid, data = scenario
    job = UseReviewJob(store)
    job._run(client=Client(), delay=0)
    row = next(r for r in inventory(store, data) if r['community_id'] == cid)
    assert row['qualification'] == 'use_conflict'
    assert row['admission_state'] == 'excluded'
    assert cid not in {c['community_id'] for c in admitted(store, data)}


def test_new_contrary_evidence_sends_a_confirmed_community_back_to_review(scenario):
    store, cid, data = scenario
    store.confirm_use(cid, revision=1, decision='residential', property_type='住宅',
                      use_evidence=[{'source': 'kerui', 'url': 'https://www.cihud.com/x/1', 'note': ''}],
                      reason='三方一致为住宅')
    assert next(r for r in inventory(store, data) if r['community_id'] == cid)['admission_state'] == 'admitted'

    job = UseReviewJob(store)
    job._run(client=Client([poi(typecode='120101', type_text='写字楼')]), delay=0)
    row = next(r for r in inventory(store, data) if r['community_id'] == cid)
    assert row['use_review']['re_review'] is True
    assert row['qualification'] == 'use_conflict'
    assert row['admission_state'] == 'excluded'
    # 已存的人工决定不被删除，也不被复核覆盖。
    assert store.admission(cid)['use_decision'] == 'residential'
    assert store.admission(cid)['use_evidence'][0]['url'] == 'https://www.cihud.com/x/1'

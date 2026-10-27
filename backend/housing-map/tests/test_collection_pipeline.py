import json

import pytest

from src.services.community_registry import CommunityRegistry, dump
from src.services.directory_policy import KEY as FLOW_KEY, VERSION as FLOW_VERSION, eligibility
from src.services.directory_position_state import identity
from src.services.directory_workflow import inventory, synchronize

RULE = 'collection-pipeline-v2'
KEY = 'collection_pipeline_version'


def master(**extra):
    return dict(community_id='c', community_name='测试住宅', district='滨江', address='月明路1076号', aliases=[],
                collection_pipeline_version=RULE, **extra)


def source(prop='住宅', **extra):
    return dict(source='tmsf', source_id='t1', name='测试住宅', district='滨江', address='月明路1076号',
                property_type=prop, listing_count=3, market_state='second_hand', **extra)


def positioned(c, typecode='120302', *, state='matched', poi_id='P1'):
    c = dict(c)
    point = dict(source_id=poi_id, name=c['community_name'], address=c['address'],
                 district='滨江', longitude=120.20749, latitude=30.20226,
                 coordinate_system='gcj02', poi_typecode=typecode, poi_type='住宅小区')
    c['amap_position'] = dict(identity=identity(c), state=state, selected=point, candidates=[point],
                              checked_at='2026-10-25T00:00:00+00:00')
    return c


def test_new_rule_requires_confirmed_poi_before_residential_admission():
    result = eligibility(master(), [source()])
    assert result['qualification'] == 'position_pending'
    assert result['workflow_state'] == 'pending'
    result = eligibility(positioned(master()), [source()])
    assert result['admission_state'] == 'admitted'
    assert result['workflow_state'] == 'admitted'


def test_legacy_rule_stays_unchanged_until_explicit_migration():
    c = master(); c.pop(KEY)
    assert eligibility(c, [source()])['admission_state'] == 'admitted'


@pytest.mark.parametrize('state,error,expected', [
    ('uncertain', '高德返回结果未完整，匹配不确定，待复核', 'incomplete'),
    ('not_found', None, 'not_found'), ('error', '异常', 'error'), ('checked', None, 'checked'),
])
def test_legacy_search_history_is_visible_but_never_subject_evidence(state, error, expected):
    from src.services.directory_position_state import position_view
    from src.services.use_review_policy import use_identity, RULE_VERSION
    from src.services.collection_pipeline import selected_review
    c = master()
    c['use_review'] = dict(identity=use_identity(c), rule_version=RULE_VERSION, state=state,
                           error=error, checked_at='2026-10-25T14:29:13Z', category='residential')
    view = position_view(c)
    assert view['state'] == 'pending' and not view.get('selected')
    assert view['query_history']['state'] == expected
    assert selected_review(c)['state'] is None
    result = eligibility(c, [source('其他')])
    assert result['workflow_state'] == 'pending'
    assert view['query_history']['message'] in result['exclusion_reason']
    assert 'query_history' not in position_view(positioned(c))  # New subject result wins.
    c['community_name'] = '另一个小区'
    assert 'query_history' not in position_view(c)  # Never attach old history to changed identity.


def test_complete_no_subject_search_is_described_as_searched_not_unqueried():
    c = master()
    c['amap_position'] = dict(identity=identity(c), state='not_found', candidates=[], checked_at='2026-10-27T00:00:00Z')
    result = eligibility(c, [source('其他')])
    assert '已查询但未找到主体地点' in result['exclusion_reason']


def test_old_loose_auto_match_has_no_grandfather_exemption():
    c = positioned(master())
    c['amap_position']['selected']['name'] += '二期'
    assert eligibility(c, [source()])['qualification'] == 'position_review'
    # An explicit human identity choice is evidence, not an automatic exemption.
    c['amap_position']['state'] = 'manual'
    assert eligibility(c, [source()])['admission_state'] == 'admitted'


def test_intersection_address_is_not_treated_as_a_doorplate_conflict():
    c = positioned(master())
    c['amap_position']['selected']['address'] = '月明路与江汉路交叉口东北角'
    assert eligibility(c, [source()])['admission_state'] == 'admitted'


@pytest.mark.parametrize(('prop', 'code'), [('写字楼', 'non_residential'), ('商铺', 'non_residential'), ('厂房', 'non_residential'), ('公寓', 'type_uncertain'),
                                         (None, 'type_missing')])
def test_unknown_and_nonresidential_are_distinguished(prop, code):
    result = eligibility(master(), [source(prop)])
    assert result['qualification'] == code
    assert result['workflow_state'] == ('excluded' if code == 'non_residential' else 'pending')


def test_selected_poi_type_is_the_only_amap_use_evidence():
    from src.services.use_review_policy import use_review_view
    c = positioned(master(), '120201')
    assert eligibility(c, [source()])['qualification'] == 'use_conflict'
    c['use_review'] = {'state': 'checked', 'category': 'residential'}
    assert use_review_view(c)['category'] == 'non_residential'
    c = positioned(master())
    c['amap_position']['candidates'].append({'source_id': 'shop', 'poi_typecode': '050000'})
    assert eligibility(c, [source()])['admission_state'] == 'admitted'


def test_manual_coordinates_cannot_invent_residential_type():
    c = positioned(master(), '', state='manual', poi_id=None)
    assert eligibility(c, [source()])['qualification'] == 'position_type_missing'


def test_manual_use_only_overrides_use_and_still_requires_a_valid_location():
    admission = dict(use_rule='use-review-v1', use_decision='residential', property_type='住宅',
                     decided_at='2026-10-26T00:00:00+00:00')
    assert eligibility(master(), [source(None)], admission=admission)['qualification'] == 'position_pending'
    c = positioned(master(), '', state='manual', poi_id=None)
    assert eligibility(c, [source(None)], admission=admission)['admission_state'] == 'admitted'
    admission['use_decision'] = 'non_residential'
    assert eligibility(master(), [source()], admission=admission)['workflow_state'] == 'excluded'


def test_existing_listing_and_newhouse_rules_survive():
    c = positioned(master())
    low = source(); low['listing_count'] = 0
    assert eligibility(c, [low])['qualification'] == 'listing_low'
    low['market_state'] = 'new_house'
    assert eligibility(c, [low])['admission_state'] == 'admitted'


def test_explicit_region_conflict_never_becomes_residential():
    c = positioned(master())
    r = source(); r['address'] = '杭州市拱墅区文晖路1号'
    assert eligibility(c, [r])['qualification'] == 'region_conflict'
    # Passing an already-projected row must not let its manual-use metadata hide region evidence.
    admission = dict(use_rule='use-review-v1', use_decision='residential', property_type='住宅',
                     decided_at='2026-10-26T00:00:00+00:00')
    c['admission'] = admission
    assert eligibility(c, [r], admission=admission)['qualification'] == 'region_conflict'


@pytest.fixture
def store(tmp_path):
    registry = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    with registry.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (FLOW_KEY, FLOW_VERSION))
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, RULE))
    return registry


def test_missing_type_source_gets_candidate_identity_before_admission(store, tmp_path):
    store.ingest(source(None))
    assert synchronize(store, tmp_path) == 1
    row = inventory(store, tmp_path)[0]
    assert not row.get('source_record_id')
    assert row['workflow_state'] == 'pending'
    assert row['qualification'] == 'type_missing'
    assert synchronize(store, tmp_path) == 0


def test_candidate_can_match_and_confirm_nonresidential_poi(store, tmp_path):
    from src.services.directory_position import position_one, position_detail, confirm_position
    store.ingest(source())
    synchronize(store, tmp_path)
    cid = inventory(store, tmp_path)[0]['community_id']

    class Client:
        def search_name(self, name, district, types=None, **kwargs):
            assert types is None
            return [dict(id='P1', name=name, adname='滨江区', typecode='120201', type='写字楼',
                         address='月明路1076号', location='120.20749,30.20226')], 1

    assert position_one(store, tmp_path, cid, Client()) == 'updated'
    row = inventory(store, tmp_path)[0]
    assert row['qualification'] == 'use_conflict'
    detail = position_detail(store, tmp_path, cid)
    assert detail['selected']['poi_typecode'] == '120201'
    confirm_position(store, tmp_path, cid, revision=detail['revision'], poi_id='P1')
    assert inventory(store, tmp_path)[0]['qualification'] == 'use_conflict'


def test_addressless_subject_can_be_verified_and_admitted(store, tmp_path):
    from src.services.directory_position import position_one, position_detail, confirm_position, PositionOutcome
    store.ingest(source())
    synchronize(store, tmp_path)
    cid = inventory(store, tmp_path)[0]['community_id']

    class Client:
        def search_name(self, name, district, types=None, **kwargs):
            return [dict(id='P1', name=name, adname='滨江区', typecode='120302', type='住宅小区',
                         address=[], location='120.20749,30.20226')], 1

    with pytest.raises(PositionOutcome):
        position_one(store, tmp_path, cid, Client())
    detail = position_detail(store, tmp_path, cid)
    assert detail['state'] == 'review'
    assert detail['review_reason'] == 'address_check'
    assert inventory(store, tmp_path)[0]['workflow_state'] == 'pending'
    confirm_position(store, tmp_path, cid, revision=detail['revision'], poi_id='P1', coordinates_verified=True)
    row = inventory(store, tmp_path)[0]
    assert row['workflow_state'] == 'admitted'
    assert row['position']['selected']['address'] == ''
    assert row['use_review']['evidence']['poi_id'] == 'P1'


def test_company_type_is_visible_as_reference_without_becoming_a_selected_subject(store, tmp_path):
    from src.services.directory_position import position_one, position_detail, PositionOutcome
    store.ingest(source('其他')); synchronize(store, tmp_path)
    cid = inventory(store, tmp_path)[0]['community_id']

    class Client:
        def search_name(self, name, district, types=None, **kwargs):
            return [dict(id='company', name=name+'通讯有限公司', adname='滨江区',
                         typecode='170200', type='公司企业;公司;公司',
                         address='六和路368号', location='120.20749,30.20226')], 1

    with pytest.raises(PositionOutcome):
        position_one(store, tmp_path, cid, Client(), force=True)
    detail = position_detail(store, tmp_path, cid)
    assert detail['reference_candidates'][0]['poi_type'] == '公司企业;公司;公司'
    assert not detail.get('selected')
    assert inventory(store, tmp_path)[0]['workflow_state'] == 'pending'
    assert '已有高德相关地点信息' in inventory(store, tmp_path)[0]['exclusion_reason']


def test_other_use_participates_in_automatic_poi_collection(store, tmp_path):
    from src.services.directory_position import PositionJob
    store.ingest(source('其他')); synchronize(store, tmp_path)

    class Client:
        calls = 0
        def search_name(self, name, district, types=None, **kwargs):
            self.calls += 1
            return [dict(id='P1', name=name, adname='滨江区', typecode='120201', type='写字楼',
                         address='月明路1076号', location='120.20749,30.20226')], 1

    client = Client()
    job = PositionJob(store)
    job.state = dict(running=True, phase='running', processed=0, total=0, updated=0, skipped=0,
                     review=0, not_found=0, failed=0, skipped_by_state={}, errors=[])
    job._run(client=client, delay=0)
    assert client.calls == 1 and job.snapshot()['total'] == 1
    row = inventory(store, tmp_path)[0]
    assert row['position']['selected']['poi_type'] == '写字楼'
    assert row['use_review']['auto_skip_reason'] is None
    assert row['workflow_state'] == 'pending'  # One unknown source is not a final negative decision.


def test_pending_other_can_be_explicitly_excluded_with_a_reason(store, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import directory_routes, directory_workflow_routes as routes
    store.ingest(source('其他')); synchronize(store, tmp_path)
    cid = inventory(store, tmp_path)[0]['community_id']
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    app = FastAPI(); app.include_router(routes.router, prefix='/api')
    with TestClient(app) as client:
        response = client.post(f'/api/directory/workflow/catalog/{cid}/exclude', json={
            'revision': 1, 'reason': '高德显示公司企业，人工确认非住宅'})
        assert response.status_code == 200, response.text
    row = inventory(store, tmp_path)[0]
    assert row['workflow_state'] == 'excluded'
    assert row['qualification'] == 'manual_exclusion'
    assert row['admission']['reason'] == '高德显示公司企业，人工确认非住宅'


def test_precise_subject_beats_shop_and_loose_containment(store, tmp_path):
    from src.services.directory_position import position_one
    store.ingest(source()); synchronize(store, tmp_path)
    cid = inventory(store, tmp_path)[0]['community_id']

    class Client:
        def search_name(self, name, district, types=None, **kwargs):
            common = dict(adname='滨江区', address='月明路1076号', location='120.20749,30.20226')
            return [dict(common, id='P1', name=name, typecode='120302'),
                    dict(common, id='shop', name=name+'便利店', typecode='060200'),
                    dict(common, id='P2', name=name+'二期', typecode='120302')], 3

    position_one(store, tmp_path, cid, Client())
    row = inventory(store, tmp_path)[0]
    assert row['admission_state'] == 'admitted'
    assert row['position']['selected']['source_id'] == 'P1'


def test_new_auto_match_replaces_historical_point_with_subject_coordinates(store, tmp_path):
    from src.services.directory_position import position_one
    c = store.create('测试住宅', district='滨江', address='月明路1076号', collection_pipeline_version=RULE,
                     longitude=120.21, latitude=30.20, coordinate_system='gcj02',
                     coordinate_evidence={'source': 'historical_amap', 'source_id': 'old'})
    r = store.ingest(source()); store.associate(r['id'], c['community_id'])

    class Client:
        def search_name(self, name, district, types=None, **kwargs):
            return [dict(id='P1', name=name, adname='滨江区', typecode='120302',
                         address='月明路1076号', location='120.20749,30.20226')], 1

    position_one(store, tmp_path, c['community_id'], Client())
    row = inventory(store, tmp_path)[0]
    assert row['coordinate_evidence']['source_id'] == 'P1'
    assert row['longitude'] == row['position']['selected']['longitude'] == 120.20749


def test_old_poi_without_type_is_requeried_instead_of_permanently_skipped(store, tmp_path):
    from src.services.directory_position import position_one
    c = store.create('测试住宅', district='滨江', address='月明路1076号', collection_pipeline_version=RULE,
                     longitude=120.20749, latitude=30.20226, coordinate_system='gcj02',
                     coordinate_evidence={'source': 'amap', 'source_id': 'P1'})
    r = store.ingest(source()); store.associate(r['id'], c['community_id'])
    assert inventory(store, tmp_path)[0]['qualification'] == 'position_type_missing'

    class Client:
        def search_name(self, name, district, types=None, **kwargs):
            return [dict(id='P1', name=name, adname='滨江区', typecode='120302',
                         address='月明路1076号', location='120.20749,30.20226')], 1

    assert position_one(store, tmp_path, c['community_id'], Client()) == 'updated'
    assert inventory(store, tmp_path)[0]['admission_state'] == 'admitted'


def test_use_review_reuses_selected_poi_without_search(store, tmp_path):
    from src.services.directory_use_review import review_one
    c = positioned(master()); store.create('测试住宅', district='滨江', address=c['address'],
        community_id='c', collection_pipeline_version=RULE, amap_position=c['amap_position'])
    r = store.ingest(source()); store.associate(r['id'], 'c')

    class Client:
        def search_name(self, *args, **kwargs):
            raise AssertionError('选定主体后不应再次按名字搜索')

    assert review_one(store, tmp_path, 'c', Client(), force=True) == 'updated'


def test_paging_budget_counts_actual_requests(store, tmp_path):
    from src.services.directory_position import PositionJob
    store.ingest(source()); synchronize(store, tmp_path)

    class Client:
        calls = 0
        def search_name(self, name, district, types=None, *, page=1):
            self.calls += 1
            return [dict(id=f'{page}-{i}', name=name if i == 0 else f'无关商户{i}',
                         adname='滨江区', typecode='120302' if i == 0 else '060200',
                         address='月明路1076号', location='120.20749,30.20226') for i in range(25)], 60

    client = Client()
    job = PositionJob(store)
    job.state = dict(running=True, phase='running', processed=0, total=0, updated=0, skipped=0,
                     review=0, not_found=0, failed=0, skipped_by_state={}, errors=[])
    job._run(client=client, delay=0, budget=2)
    assert client.calls == 2
    assert job.snapshot()['requests'] == 2
    assert inventory(store, tmp_path)[0]['admission_state'] == 'excluded'
    assert job.snapshot()['failed'] == 0
    assert inventory(store, tmp_path)[0]['position']['state'] == 'pending'
    assert job.snapshot()['retryable'] == 0
    assert job.snapshot()['phase'] == 'budget_exhausted'


def test_retry_scope_and_live_count_ignore_old_job_failures_and_protected_states(store, tmp_path):
    from src.services.directory_position import PositionJob
    def add(name, state, reason=None, error=None):
        c = store.create(name, district='滨江', address='月明路1076号', collection_pipeline_version=RULE)
        s = store.ingest({**source(), 'name': name, 'source_id': name})
        store.associate(s['id'], c['community_id'])
        with store.db() as db:
            payload = json.loads(db.execute('SELECT payload FROM communities WHERE id=?', (c['community_id'],)).fetchone()[0])
            payload['amap_position'] = dict(identity=identity(c), state=state, candidates=[], review_reason=reason,
                                            error=error, checked_at='2026-10-27T00:00:00Z')
            db.execute('UPDATE communities SET payload=? WHERE id=?', (dump(payload), c['community_id']))
        return c['community_id']
    add('失败小区', 'error')
    add('分页小区', 'review', 'results_incomplete')
    add('待确认小区', 'review', 'multiple_subjects')
    add('人工确认小区', 'manual')
    add('未找到小区', 'not_found')
    add('预算小区', 'error', error='达到本轮高德实际请求预算，未完成目标可下次重试')
    excluded = add('人工排除小区', 'error')
    revision = next(r for r in inventory(store, tmp_path) if r['community_id'] == excluded)['admission']['revision']
    store.decide_admission(excluded, 'exclude', revision=revision, reason='人工确认不收录')
    job = PositionJob(store)
    job.state = dict(running=True, phase='running', processed=0, total=0, updated=0, skipped=0,
                     review=0, not_found=0, failed=99, skipped_by_state={}, errors=[])
    assert job.snapshot()['retryable'] == 2
    class Client:
        queries = []
        def search_name(self, name, *args, **kwargs):
            self.queries.append(name)
            return [dict(id=name, name=name, adname='滨江区', typecode='120302',
                         address='月明路1076号', location='120.20749,30.20226')], 1
    client = Client()
    job.state['failed'] = 0
    job._run(client=client, delay=0, mode='retry_failed')
    assert set(client.queries) == {'失败小区', '分页小区'}
    assert job.snapshot()['total'] == 2 and job.snapshot()['updated'] == 2
    assert job.snapshot()['retryable'] == 0
    client.queries.clear()
    job._run(client=client, delay=0, mode='retry_failed')
    assert client.queries == [] and job.snapshot()['total'] == 0


def test_automatic_retry_rechecks_manual_exclusion_before_query(store, tmp_path):
    from src.services.directory_position import position_one
    store.ingest(source()); synchronize(store, tmp_path)
    row = inventory(store, tmp_path)[0]
    store.decide_admission(row['community_id'], 'exclude', revision=row['admission']['revision'], reason='人工确认不收录')
    class Client:
        def search_name(self, *args, **kwargs):
            raise AssertionError('人工排除后不得发起自动查询')
    assert position_one(store, tmp_path, row['community_id'], Client(), automatic=True) == 'skipped'


def test_position_start_api_accepts_retry_mode_and_keeps_no_body_compatibility(store, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import directory_workflow_routes as routes
    modes = []
    class Job:
        def start(self, mode='all'):
            modes.append(mode)
            return dict(running=True, mode=mode)
    monkeypatch.setattr(routes, '_position', Job())
    app = FastAPI(); app.include_router(routes.router, prefix='/api')
    with TestClient(app) as client:
        assert client.post('/api/directory/workflow/positions').status_code == 202
        assert client.post('/api/directory/workflow/positions', json={'mode': 'retry_failed'}).status_code == 202
        assert client.post('/api/directory/workflow/positions', json={'mode': 'invalid'}).status_code == 422
    assert modes == ['all', 'retry_failed']


def test_incomplete_query_is_retryable_but_not_counted_as_manual_review(store, tmp_path):
    from src.services.directory_position import PositionJob
    store.ingest(source()); synchronize(store, tmp_path)
    class Client:
        def search_name(self, name, *args, **kwargs):
            return [dict(id='P1', name=name, adname='滨江区', typecode='120302',
                         address='月明路1076号', location='120.20749,30.20226')], 30
    job = PositionJob(store)
    job.state = dict(running=True, phase='running', processed=0, total=0, updated=0, skipped=0,
                     review=0, not_found=0, failed=0, skipped_by_state={}, errors=[])
    job._run(client=Client(), delay=0)
    state = job.snapshot()
    assert state['incomplete'] == state['retryable'] == 1
    assert state['failed'] == state['review'] == 0
    assert state['phase'] == 'partial_failed'


def test_empty_failure_retry_is_lazy_and_legacy_history_is_classified_correctly(store, monkeypatch):
    from src.services.directory_position import PositionJob, query_retryable
    def no_key():
        raise AssertionError('无失败项不能创建高德客户端')
    monkeypatch.setattr('src.services.directory_position.AmapClient', no_key)
    job = PositionJob(store)
    job.state = dict(running=True, phase='running', processed=0, total=0, updated=0, skipped=0,
                     review=0, not_found=0, failed=0, skipped_by_state={}, errors=[])
    job._run(delay=0, mode='retry_failed')
    assert job.snapshot()['phase'] == 'succeeded' and job.snapshot()['total'] == 0
    assert query_retryable(dict(state='pending', query_history={'state': 'incomplete'}))
    assert query_retryable(dict(state='pending', query_history={'state': 'error'}))
    assert not query_retryable(dict(state='pending', query_history={'state': 'not_found'}))
    assert not query_retryable(dict(state='review', error='候选有歧义、地址不同或结果未完整返回'))


@pytest.mark.parametrize('kind', ['two_subjects', 'wrong_address', 'phase_only'])
def test_ambiguous_subjects_need_human_confirmation(store, tmp_path, kind):
    from src.services.directory_position import position_one, PositionOutcome
    store.ingest(source()); synchronize(store, tmp_path)
    cid = inventory(store, tmp_path)[0]['community_id']

    class Client:
        def search_name(self, name, district, types=None, **kwargs):
            p = dict(id='P1', name=name, adname='滨江区', typecode='120302',
                     address='月明路1076号', location='120.20749,30.20226')
            if kind == 'two_subjects':
                return [p, dict(p, id='P2')], 2
            if kind == 'wrong_address':
                p['address'] = '滨文路500号'
            else:
                p['name'] += '二期'
            return [p], 1

    with pytest.raises(PositionOutcome) as exc:
        position_one(store, tmp_path, cid, Client())
    assert exc.value.state == 'review'
    expected_reason = {'two_subjects': 'multiple_subjects', 'wrong_address': 'address_check', 'phase_only': 'name_mismatch'}[kind]
    assert exc.value.reason == expected_reason
    row = inventory(store, tmp_path)[0]
    assert row['position']['review_reason'] == expected_reason
    assert '结果未完整返回' not in row['position']['error']
    assert row['workflow_state'] == 'pending'
    assert not row.get('coordinate_evidence')


def test_migration_preview_apply_and_rollback_preserve_sources(tmp_path):
    from src.services.collection_pipeline_migration import preview, apply, rollback
    path = tmp_path / 'data'; path.mkdir()
    registry = CommunityRegistry(path / 'community_registry.sqlite3')
    with registry.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (FLOW_KEY, FLOW_VERSION))
    c = registry.create('测试住宅', district='滨江', address='月明路1076号')
    r = registry.ingest(source()); registry.associate(r['id'], c['community_id'])
    assert inventory(registry, path)[0]['admission_state'] == 'admitted'
    before = registry.path.read_bytes()
    plan = preview(path)
    assert registry.path.read_bytes() == before
    assert plan['totals']['withdrawn'] == 1
    assert plan['changes'][0]['workflow_state'] == 'pending'
    with pytest.raises(ValueError, match='维护'):
        apply(path, plan, tmp_path / 'backup')
    apply(path, plan, tmp_path / 'backup', maintenance=True)
    row = inventory(registry, path)[0]
    assert row['workflow_state'] == 'pending'
    assert row['community_id'] == c['community_id']
    assert registry.sources()[0]['id'] == r['id']
    assert apply(path, preview(path), tmp_path / 'unused-backup', maintenance=True)['already_applied']
    assert not (tmp_path / 'unused-backup').exists()
    rollback(path, tmp_path / 'backup', maintenance=True)
    assert inventory(registry, path)[0]['admission_state'] == 'admitted'


def test_migration_refuses_stale_preview_and_rollback_after_new_writes(tmp_path):
    from src.services.collection_pipeline_migration import preview, apply, rollback
    path = tmp_path / 'data'; path.mkdir()
    registry = CommunityRegistry(path / 'community_registry.sqlite3')
    with registry.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (FLOW_KEY, FLOW_VERSION))
    plan = preview(path)
    registry.ingest(source())
    with pytest.raises(ValueError, match='快照'):
        apply(path, plan, tmp_path / 'stale-backup', maintenance=True)
    apply(path, preview(path), tmp_path / 'backup', maintenance=True)
    registry.ingest(source('其他', source_kind='project'))
    with pytest.raises(ValueError, match='新数据'):
        rollback(path, tmp_path / 'backup', maintenance=True)


def test_candidate_api_can_query_before_admission_and_reclassifies(store, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import directory_routes, directory_workflow_routes as routes
    store.ingest(source()); synchronize(store, tmp_path)
    cid = inventory(store, tmp_path)[0]['community_id']

    class Client:
        def search_name(self, name, district, types=None, **kwargs):
            return [dict(id='P1', name=name, adname='滨江区', typecode='120302', type='住宅小区',
                         address='月明路1076号', location='120.20749,30.20226')], 1
        def close(self): pass

    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    monkeypatch.setattr(routes, '_position', None)
    monkeypatch.setattr(routes, '_use_review', None)
    monkeypatch.setattr('src.services.directory_position.AmapClient', Client)
    app = FastAPI(); app.include_router(routes.router, prefix='/api')
    with TestClient(app) as client:
        base = '/api/directory/workflow'
        pending = client.get(base + '/catalog?state=excluded&workflow=pending').json()['data']
        assert pending['total'] == 1
        assert client.get(f'{base}/catalog/{cid}/position').status_code == 200
        response = client.post(f'{base}/catalog/{cid}/position/query')
        assert response.status_code == 200, response.text
        assert response.json()['data']['selected']['source_id'] == 'P1'
        admitted = client.get(base + '/catalog?state=admitted&workflow=admitted').json()['data']
        assert admitted['total'] == 1
        assert admitted['items'][0]['use_review']['evidence']['poi_id'] == 'P1'
        assert client.get(base + '/catalog?state=excluded&workflow=pending').json()['data']['total'] == 0


def test_zero_count_suggestion_allows_alias_subject_lookup(store, tmp_path):
    from src.services.directory_position import position_one, position_detail
    store.ingest(source())
    synchronize(store, tmp_path)
    cid = inventory(store, tmp_path)[0]['community_id']
    c = store.communities()[0]
    store.update(cid, name=c['community_name'], aliases=['测试别名'])

    class Client:
        queries = []
        def search_name(self, name, district, **kwargs):
            self.queries.append(name)
            if name == '测试住宅':
                return [dict(name='地址建议', location='120,30')], 0
            return [dict(id='P1', name='测试别名', adname='滨江区', typecode='120302',
                         address='月明路1076号', location='120.20749,30.20226')], 1
    client = Client()
    assert position_one(store, tmp_path, cid, client) == 'updated'
    assert client.queries == ['测试住宅', '测试别名']
    assert position_detail(store, tmp_path, cid)['selected']['source_id'] == 'P1'

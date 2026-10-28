"""轮廓工作流:任务、候选、人工覆盖层与撤销的行为测试。

全部用隔离数据目录自造小区与基础轮廓,不依赖线上数据、注册库快照或真实 Overpass。
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import boundary_workflow_routes
from src.services import boundary_estimate, boundary_workflow, boundary_workflow_store, data_loader
from src.services.boundary_estimate import EstimateOutcome
from src.services.community_directory import prepare_directory

RING = [[120.2070, 30.2020], [120.2090, 30.2020], [120.2090, 30.2040], [120.2070, 30.2040], [120.2070, 30.2020]]
OTHER_RING = [[120.2100, 30.2020], [120.2110, 30.2020], [120.2110, 30.2030], [120.2100, 30.2030], [120.2100, 30.2020]]


class FakeExecutor:
    """不真正起线程的假执行器:只记录任务,测试手动驱动。"""

    def __init__(self, *, accept=True):
        self.jobs: list[str] = []
        self.accept = accept

    def start(self):
        pass

    def submit(self, job_id: str) -> bool:
        if not self.accept:
            return False
        self.jobs.append(job_id)
        return True

    def pending(self) -> int:
        return len(self.jobs)


def seed_world(tmp_path, monkeypatch, *, polygons=None, community_id='100'):
    """造一个最小展示集合:一个住宅小区 + 坐标 + 可选基础轮廓。"""
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([
        dict(community_id=community_id, community_name='江汉路小区', district='滨江',
             address='杭州市滨江区江汉路')], ensure_ascii=False), encoding='utf-8')
    (tmp_path / 'property_types.json').write_text(json.dumps(
        {community_id: {'property_type': '住宅'}}, ensure_ascii=False), encoding='utf-8')
    (tmp_path / 'binjiang_coordinates.json').write_text(json.dumps({community_id: dict(
        longitude=120.207490, latitude=30.202261,
        formatted_address='杭州市滨江区江汉路')}, ensure_ascii=False), encoding='utf-8')
    (tmp_path / 'binjiang_polygons_merged.json').write_text(
        json.dumps(polygons or {}, ensure_ascii=False), encoding='utf-8')
    prepare_directory(tmp_path)
    monkeypatch.setattr(data_loader, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(boundary_workflow_store, 'WORKFLOW_DB', tmp_path / 'workflow.sqlite3')
    monkeypatch.setattr(boundary_estimate, 'CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(boundary_workflow, '_executor_instance', FakeExecutor())
    return community_id


def fake_estimate(monkeypatch, *, ring=None, outcome=None):
    """替换真实估算,不触网。"""
    if outcome is None:
        outcome = EstimateOutcome(
            ring=ring or RING, members=(), building_faces=2, residential_faces=0,
            dropped_parts=0, low_confidence=False, warnings=(), area_ha=1.5)
    monkeypatch.setattr(boundary_workflow, 'estimate_one', lambda *args, **kwargs: outcome)


def drain_jobs():
    """把已入队的任务同步跑完。"""
    executor = boundary_workflow._executor_instance
    for job_id in list(executor.jobs):
        boundary_workflow._run_job(job_id)
    executor.jobs.clear()


@pytest.fixture()
def world(tmp_path, monkeypatch):
    cid = seed_world(tmp_path, monkeypatch)
    fake_estimate(monkeypatch)
    return cid


def test_effective_view_overlays_manual_confirmation(world, tmp_path):
    base = {world: {'source': 'osm', 'rings': [RING]}}
    (tmp_path / 'binjiang_polygons_merged.json').write_text(
        json.dumps(base, ensure_ascii=False), encoding='utf-8')
    assert boundary_workflow.effective_polygons()[world]['source'] == 'osm'

    status, payload = boundary_workflow.create_estimate(world)
    assert status == 202
    drain_jobs()
    candidate_id = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    revision = boundary_workflow.effective_revision(world)
    applied = boundary_workflow.apply_candidate(candidate_id, revision, 'op-1')
    assert applied['community_id'] == world
    effective = boundary_workflow.effective_polygons()[world]
    assert effective['source'] == 'osm-building'
    assert effective['rings'] == [RING]
    # 应用返回的 revision 必须等于写入后的实际 revision(提交前预算是准的)
    assert applied['revision'] == boundary_workflow.effective_revision(world)
    # 基础文件没有被改写
    assert json.loads((tmp_path / 'binjiang_polygons_merged.json').read_text(encoding='utf-8'))[world]['source'] == 'osm'


def test_missing_boundary_detection_matches_map_rule(world, tmp_path):
    (tmp_path / 'binjiang_polygons_merged.json').write_text(
        json.dumps({world: {'source': 'shp', 'rings': [RING]}}, ensure_ascii=False), encoding='utf-8')
    state = boundary_workflow.community_state(world)
    assert state['has_visible_boundary'] is False
    assert state['base_has_boundary'] is False
    assert boundary_workflow.is_displayable({'source': 'shp', 'rings': [RING]}) is False
    assert boundary_workflow.is_displayable({'source': 'osm', 'rings': [RING]}) is True
    assert boundary_workflow.is_displayable({'source': 'osm', 'rings': []}) is False


def test_apply_requires_matching_revision(world):
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    candidate_id = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    with pytest.raises(boundary_workflow.WorkflowError) as error:
        boundary_workflow.apply_candidate(candidate_id, 'stale-revision', 'op-1')
    assert error.value.status_code == 409
    assert error.value.code == 'revision_conflict'


def test_apply_is_idempotent_for_same_operation_id(world):
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    candidate_id = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    revision = boundary_workflow.effective_revision(world)
    first = boundary_workflow.apply_candidate(candidate_id, revision, 'op-1')
    second = boundary_workflow.apply_candidate(candidate_id, revision, 'op-1')
    assert first == second


def test_second_window_apply_conflicts(world):
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    candidate_id = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    revision = boundary_workflow.effective_revision(world)
    boundary_workflow.apply_candidate(candidate_id, revision, 'op-1')
    # 另一个窗口拿着旧版本号再应用 -> 冲突,不能覆盖
    with pytest.raises(boundary_workflow.WorkflowError) as error:
        boundary_workflow.apply_candidate(candidate_id, revision, 'op-2')
    assert error.value.status_code == 409


def test_candidate_goes_stale_when_base_changes(world, tmp_path):
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    candidate_id = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    # 生成之后基础轮廓被重建改动
    (tmp_path / 'binjiang_polygons_merged.json').write_text(
        json.dumps({world: {'source': 'osm', 'rings': [OTHER_RING]}}, ensure_ascii=False), encoding='utf-8')
    state = boundary_workflow.candidate_state(candidate_id)
    assert state['stale'] is True
    assert state['applicable'] is False
    with pytest.raises(boundary_workflow.WorkflowError) as error:
        boundary_workflow.apply_candidate(candidate_id, state['revision'], 'op-1')
    assert error.value.code == 'candidate_stale'


def test_revert_restores_previous_state(world, tmp_path):
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    candidate_id = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    revision = boundary_workflow.effective_revision(world)
    applied = boundary_workflow.apply_candidate(candidate_id, revision, 'op-1')
    assert boundary_workflow.community_state(world)['has_visible_boundary'] is True
    current = boundary_workflow.effective_revision(world)
    reverted = boundary_workflow.revert_community(world, current, 'op-1', 'op-revert-1')
    assert reverted['community_id'] == world
    assert reverted['revision'] == boundary_workflow.effective_revision(world)
    state = boundary_workflow.community_state(world)
    assert state['has_visible_boundary'] is False
    assert state['override'] is None
    assert state['revertable'] is None


def test_revert_conflicts_when_base_changed_after_apply(world, tmp_path):
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    candidate_id = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    revision = boundary_workflow.effective_revision(world)
    boundary_workflow.apply_candidate(candidate_id, revision, 'op-1')
    stale_revision = boundary_workflow.effective_revision(world)
    (tmp_path / 'binjiang_polygons_merged.json').write_text(
        json.dumps({world: {'source': 'osm', 'rings': [OTHER_RING]}}, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(boundary_workflow.WorkflowError) as error:
        boundary_workflow.revert_community(world, stale_revision, 'op-1', 'op-revert-1')
    assert error.value.status_code == 409
    assert error.value.code == 'revision_conflict'


def test_revert_is_idempotent(world):
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    candidate_id = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    revision = boundary_workflow.effective_revision(world)
    boundary_workflow.apply_candidate(candidate_id, revision, 'op-1')
    current = boundary_workflow.effective_revision(world)
    first = boundary_workflow.revert_community(world, current, 'op-1', 'op-revert-1')
    second = boundary_workflow.revert_community(world, current, 'op-1', 'op-revert-1')
    assert first == second


def test_reject_is_idempotent_and_refuses_applied(world):
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    candidate_id = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    revision = boundary_workflow.effective_revision(world)
    first = boundary_workflow.reject_candidate(candidate_id, revision)
    second = boundary_workflow.reject_candidate(candidate_id, revision)
    assert first['status'] == 'rejected'
    assert second['status'] == 'rejected'
    # 被拒绝的候选不能再应用
    with pytest.raises(boundary_workflow.WorkflowError) as error:
        boundary_workflow.apply_candidate(candidate_id, revision, 'op-1')
    assert error.value.code == 'candidate_state_conflict'


def test_reject_does_not_touch_applied_candidate(world):
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    candidate_id = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    revision = boundary_workflow.effective_revision(world)
    boundary_workflow.apply_candidate(candidate_id, revision, 'op-1')
    with pytest.raises(boundary_workflow.WorkflowError) as error:
        boundary_workflow.reject_candidate(candidate_id, boundary_workflow.effective_revision(world))
    assert error.value.code == 'candidate_state_conflict'


def test_duplicate_request_reuses_same_job(world):
    status, payload = boundary_workflow.create_estimate(world)
    again_status, again = boundary_workflow.create_estimate(world)
    assert status == 202
    assert again_status == 200
    assert again['job_id'] == payload['job_id']
    assert again['reused'] is True


def test_regenerate_supersedes_previous_candidate(world):
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    first_candidate = boundary_workflow.job_state(payload['job_id'])['candidate_id']
    assert boundary_workflow.candidate_state(first_candidate)['status'] == 'ready'
    status, payload = boundary_workflow.create_estimate(world, regenerate=True)
    assert status == 202
    assert boundary_workflow.candidate_state(first_candidate)['status'] == 'superseded'


def test_queue_full_reports_conflict(world):
    boundary_workflow._executor_instance = FakeExecutor(accept=False)
    with pytest.raises(boundary_workflow.WorkflowError) as error:
        boundary_workflow.create_estimate(world)
    assert error.value.status_code == 409
    assert error.value.code == 'queue_full'


def test_unknown_community_is_not_found(world):
    with pytest.raises(boundary_workflow.WorkflowError) as error:
        boundary_workflow.create_estimate('999')
    assert error.value.status_code == 404


def test_restart_marks_inflight_jobs_interrupted(world):
    boundary_workflow.create_estimate(world)
    assert boundary_workflow.recover_interrupted_jobs() == 1
    job = boundary_workflow.job_state(boundary_workflow._executor_instance.jobs[0])
    assert job['phase'] == 'interrupted'
    assert job['error_code'] == 'interrupted'


def test_failed_estimate_records_error_code(world, monkeypatch):
    from src.services.boundary_estimate import EstimateError

    def boom(*args, **kwargs):
        raise EstimateError('no_geometry', '该定位附近没有可用的建筑面')

    monkeypatch.setattr(boundary_workflow, 'estimate_one', boom)
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    job = boundary_workflow.job_state(payload['job_id'])
    assert job['phase'] == 'failed'
    assert job['error_code'] == 'no_geometry'


def test_invalid_geometry_is_rejected_before_candidate(world, monkeypatch):
    fake_estimate(monkeypatch, outcome=EstimateOutcome(
        ring=[[121.9, 30.9], [121.91, 30.9], [121.91, 30.91], [121.9, 30.91], [121.9, 30.9]],
        members=(), building_faces=1, residential_faces=0, dropped_parts=0,
        low_confidence=False, warnings=(), area_ha=1.0))
    status, payload = boundary_workflow.create_estimate(world)
    drain_jobs()
    job = boundary_workflow.job_state(payload['job_id'])
    assert job['phase'] == 'failed'
    assert job['error_code'] == 'invalid_geometry'


# ---------------------------------------------------------------------------
# HTTP 接口
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(world):
    app = FastAPI()
    app.include_router(boundary_workflow_routes.router, prefix='/api')
    return TestClient(app)


def test_http_flow_needs_no_token(client, world):
    state = client.get(f'/api/communities/{world}/boundary-workflow')
    assert state.status_code == 200
    assert state.json()['data']['community_id'] == world

    created = client.post(f'/api/communities/{world}/boundary-estimates', json={})
    assert created.status_code == 202
    job_id = created.json()['data']['job_id']
    for job in list(boundary_workflow._executor_instance.jobs):
        boundary_workflow._run_job(job)
    boundary_workflow._executor_instance.jobs.clear()

    job = client.get(f'/api/boundary-estimates/{job_id}').json()['data']
    assert job['phase'] == 'succeeded'
    candidate_id = job['candidate_id']

    candidate = client.get(f'/api/boundary-candidates/{candidate_id}').json()['data']
    assert candidate['rings'] == [RING]
    assert candidate['community_id'] == world

    applied = client.post(f'/api/boundary-candidates/{candidate_id}/apply',
                          json={'expected_revision': candidate['revision'], 'operation_id': 'op-http-1'})
    assert applied.status_code == 200
    assert applied.json()['data']['community_id'] == world

    after = client.get(f'/api/communities/{world}/boundary-workflow').json()['data']
    assert after['has_visible_boundary'] is True
    assert after['revertable']['operation_id'] == 'op-http-1'

    reverted = client.post(f'/api/communities/{world}/boundary-reverts',
                           json={'expected_revision': after['revision'],
                                 'apply_operation_id': 'op-http-1', 'operation_id': 'op-http-2'})
    assert reverted.status_code == 200
    assert client.get(f'/api/communities/{world}/boundary-workflow').json()['data']['has_visible_boundary'] is False


def test_http_unknown_community_returns_404(client):
    assert client.get('/api/communities/404/boundary-workflow').status_code == 404
    assert client.post('/api/communities/404/boundary-estimates', json={}).status_code == 404


def test_http_apply_conflict_returns_409(client, world):
    created = client.post(f'/api/communities/{world}/boundary-estimates', json={}).json()['data']
    for job in list(boundary_workflow._executor_instance.jobs):
        boundary_workflow._run_job(job)
    boundary_workflow._executor_instance.jobs.clear()
    candidate_id = boundary_workflow.job_state(created['job_id'])['candidate_id']
    response = client.post(f'/api/boundary-candidates/{candidate_id}/apply',
                           json={'expected_revision': 'wrong', 'operation_id': 'op-x'})
    assert response.status_code == 409


def test_old_import_route_still_requires_token(client, world, monkeypatch):
    """旧批量导入接口的鉴权行为不受新流程影响。"""
    from src.api import boundary_import_routes
    monkeypatch.setenv('HOUSING_ADMIN_TOKEN', 'secret')
    app = FastAPI()
    app.include_router(boundary_import_routes.router, prefix='/api')
    guarded = TestClient(app)
    response = guarded.post('/api/boundaries/import', json={'source': 'osm-building', 'boundaries': []})
    assert response.status_code == 401

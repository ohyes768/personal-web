import pytest

from src.services.collection_pipeline import pending_operation_bucket


def row(qualification, **extra):
    return {'community_id': qualification, 'community_name': qualification, 'qualification': qualification,
            'admission_state': 'excluded', 'workflow_state': 'pending', 'district': '滨江', 'sources': [], **extra}


@pytest.mark.parametrize('qualification', ['position_pending', 'position_review', 'position_type_missing'])
def test_position_qualifications_are_location_work(qualification):
    assert pending_operation_bucket(row(qualification)) == 'position'


@pytest.mark.parametrize('position', [
    {'selected': None},
    {'state': 'not_found'},
    {'state': 'error'},
    {'state': 'review'},
    {'state': 'pending'},
    {'query_history': {'state': 'error'}},
    {'state': 'error', 'query_history': {'state': 'checked'}},
])
def test_type_uncertain_without_a_selected_subject_is_location_work(position):
    assert pending_operation_bucket(row('type_uncertain', position=position)) == 'position'


def test_type_uncertain_with_a_selected_subject_or_no_position_is_use_work():
    assert pending_operation_bucket(row('type_uncertain', position={'selected': {'poi_id': 'B1'}})) == 'use'
    assert pending_operation_bucket(row('type_uncertain')) == 'use'


@pytest.mark.parametrize('qualification', ['use_conflict', 'use_uncertain'])
def test_use_qualifications_stay_in_the_use_bucket(qualification):
    assert pending_operation_bucket(row(qualification)) == 'use'


@pytest.mark.parametrize('qualification', [
    'type_conflict', 'type_missing', 'missing_tmsf', 'identity_conflict', 'identity_pending',
    'district_missing', 'address_missing', 'listing_missing', 'region_conflict', 'unknown_qualification',
])
def test_data_and_unknown_qualifications_fall_back_to_facts(qualification):
    assert pending_operation_bucket(row(qualification)) == 'facts'


def test_catalog_operation_filters_pending_rows_before_paging(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api import directory_routes, directory_workflow_routes as routes
    from src.services.community_registry import CommunityRegistry
    from src.services.directory_policy import KEY, VERSION

    store = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    with store.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    rows = [
        row('position_pending'),
        row('position_review', community_id='review'),
        row('type_uncertain', community_id='unselected', position={'state': 'not_found'}),
        row('type_uncertain', community_id='selected', position={'selected': {'poi_id': 'B1'}}),
        row('use_conflict'),
        row('type_missing'),
        row('region_conflict', community_id='region'),
        row('unknown_qualification', community_id='unknown'),
        {**row('position_pending', community_id='admitted-position'), 'admission_state': 'admitted', 'workflow_state': 'admitted'},
    ]
    monkeypatch.setattr(directory_routes, 'store', lambda: store)
    monkeypatch.setattr(routes.flow, 'inventory', lambda registry, data_dir: rows)
    app = FastAPI()
    app.include_router(routes.router, prefix='/api')
    client = TestClient(app)
    base = '/api/directory/workflow/catalog?state=excluded&workflow=pending'

    def ids(operation, **extra):
        query = '&'.join(f'{key}={value}' for key, value in extra.items())
        suffix = f'&{query}' if query else ''
        response = client.get(f'{base}&operation={operation}{suffix}')
        assert response.status_code == 200, response.text
        data = response.json()['data']
        return data['total'], [item['community_id'] for item in data['items']]

    assert ids('position') == (3, ['position_pending', 'review', 'unselected'])
    assert ids('use') == (2, ['selected', 'use_conflict'])
    assert ids('facts') == (3, ['type_missing', 'region', 'unknown'])
    assert ids('facts', page_size=1) == (3, ['type_missing'])
    assert client.get(f'{base}&operation=bogus').status_code == 422
    everything = client.get(base).json()['data']
    assert everything['total'] == 8

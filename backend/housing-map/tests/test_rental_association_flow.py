"""Eligibility and the human skip/reopen decisions survive the Fang retirement."""
import pytest
from src.services.community_registry import CommunityRegistry
from src.services.rental_reference.association import (
    decide,
    eligible_communities,
    read_review,
)
from src.services.rental_reference.refresh import RentalRefreshService


def setup(tmp_path):
    registry = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    for cid, name in [('c1', '测试花园'), ('c2', '其他花园')]:
        registry.create(name, district='滨江', address='测试路1号', community_id=cid)
        record = registry.ingest(dict(source='tmsf', source_id=cid, name=name, district='滨江',
                                      property_type='住宅', market_state='second_hand', listing_count=3))
        registry.associate(record['id'], cid)
    return registry


def test_eligibility_excludes_community_without_address(tmp_path):
    registry = setup(tmp_path)
    registry.create('待核实', district='滨江', community_id='c3')
    eligible, total = eligible_communities(registry)
    assert {c['community_id'] for c in eligible} == {'c1', 'c2'}
    assert total == 3


def test_skip_is_persisted_and_survives_a_restart(tmp_path):
    registry = setup(tmp_path)
    decide(registry, 'c1', 'skip')
    reopened = CommunityRegistry(registry.path)
    assert read_review(reopened, 'c1')['decision'] == 'skipped'
    assert len(reopened.communities()) == 2


def test_reopen_clears_the_skip(tmp_path):
    registry = setup(tmp_path)
    decide(registry, 'c1', 'skip')
    decide(registry, 'c1', 'reopen')
    assert read_review(registry, 'c1')['decision'] != 'skipped'


def test_bind_is_retired(tmp_path):
    registry = setup(tmp_path)
    with pytest.raises(ValueError, match='幸福里'):
        decide(registry, 'c1', 'bind')


def test_skip_rejects_a_community_that_already_has_a_source(tmp_path):
    registry = setup(tmp_path)
    source = registry.ingest(dict(source='xingfuli', source_id='101', name='测试花园',
                                  seed_listing_id='101', auto_association_disabled=True))
    registry.associate(source['id'], 'c1')
    with pytest.raises(ValueError, match='已绑定'):
        decide(registry, 'c1', 'skip')


def test_review_api_skip_reopen_and_retired_bind(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import rental_source_routes, rental_routes
    registry = setup(tmp_path)
    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                                    delay=0)
    monkeypatch.setattr(rental_routes, '_mappings_path', tmp_path / 'rental_community_mappings.json')
    monkeypatch.setattr(rental_routes, '_get_service', lambda: service)
    app = FastAPI(); app.include_router(rental_source_routes.router)
    client = TestClient(app)
    assert client.post('/rentals/association-tasks/c1', json={'action': 'skip'}).status_code == 200
    assert client.get('/rentals/association-tasks').json()['data']['items'][0]['reason'] == 'skipped'
    assert client.post('/rentals/association-tasks/c1', json={'action': 'bind',
                                                               'candidate_id': '101'}).status_code == 410
    assert client.post('/rentals/association-tasks/c1', json={'action': 'reopen'}).status_code == 200
    remaining = client.get('/rentals/association-tasks').json()['data']['items']
    assert {i['community_id'] for i in remaining} == {'c1', 'c2'}
    assert remaining[0]['reason'] == 'missing'


def test_review_api_reports_associated_count(tmp_path, monkeypatch):
    """已关联幸福里来源的小区不在清单里，但接口必须报出它们的数量，否则页面无处看已采集总数。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import rental_source_routes, rental_routes
    registry = setup(tmp_path)
    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                                    delay=0)
    monkeypatch.setattr(rental_routes, '_mappings_path', tmp_path / 'rental_community_mappings.json')
    monkeypatch.setattr(rental_routes, '_get_service', lambda: service)
    app = FastAPI(); app.include_router(rental_source_routes.router)
    client = TestClient(app)
    source = registry.ingest(dict(source='xingfuli', source_id='101', name='测试花园',
                                  seed_listing_id='101', auto_association_disabled=True))
    registry.associate(source['id'], 'c1')
    data = client.get('/rentals/association-tasks').json()['data']
    assert {i['community_id'] for i in data['items']} == {'c2'}
    assert data['associated_count'] == 1


def test_matching_review_list_keeps_the_human_skip(tmp_path):
    from src.services.rental_reference.matching import source_reviews
    registry = setup(tmp_path)
    decide(registry, 'c1', 'skip')
    items = {i['community_id']: i for i in source_reviews(registry)}
    assert items['c1']['reason'] == 'skipped'
    assert items['c2']['reason'] == 'missing'

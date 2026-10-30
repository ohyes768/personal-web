from types import SimpleNamespace

from src.api import directory_routes, directory_workflow_routes as routes
from src.services import community_enrichment


def test_retry_returns_materialized_identity_without_querying_position(tmp_path, monkeypatch):
    source = {'id': 't1', 'source': 'tmsf', 'community_id': None}
    registry = SimpleNamespace(path=tmp_path / 'registry.sqlite', sources=lambda: [source])
    monkeypatch.setattr(routes, 'require_store', lambda: registry)
    monkeypatch.setattr(directory_routes, 'job', lambda: SimpleNamespace(state=None))
    monkeypatch.setattr(routes.flow, 'inventory', lambda *_: [
        {'community_id': 'source-t1', 'sources': [source]}])
    monkeypatch.setattr(routes.flow, 'synchronize', lambda *_: source.update(community_id='formal-id'))
    calls = []
    def enrich(*args, **kwargs):
        calls.append((args[2], kwargs))
        return {'source_id': 't1', 'errors': ['保留上次证据']}
    monkeypatch.setattr(community_enrichment, 'enrich_source', enrich)
    packet = routes.retry('source-t1')
    assert packet['data']['community_id'] == 'formal-id'
    assert packet['data']['errors'] == ['保留上次证据']
    assert calls == [('t1', {'include_position': False})]

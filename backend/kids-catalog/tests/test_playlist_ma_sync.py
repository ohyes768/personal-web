import threading
import pytest
from src.audio_tags import read_tags
from src.music_assistant import MAError
from test_device_collections import setup, add_album, confirm, generate, generate_selected


def test_generation_tags_selected_and_rebuilds_ledger(setup):
    client,app,catalog,root=setup
    p=add_album(root,catalog,'听，小蜗牛艾玛',2)
    q=add_album(root,catalog,'未选择',1)
    confirm(client,p.name);confirm(client,q.name)
    result=generate_selected(client,[p.name])
    assert result['generation']['status']=='done'
    assert result['generation']['integration']['tags_updated']==2
    assert read_tags(p/'001-曲目.mp3')['album']==[p.name]
    assert read_tags(q/'001-曲目.mp3')['album']==[]
    again=generate_selected(client,[p.name])
    assert again['generation']['status']=='done'
    assert again['generation']['integration']['tags_updated']==0
    assert again['snapshot']['items']==result['snapshot']['items']


def test_ma_error_does_not_claim_ready_or_discard_directory(setup):
    client,app,catalog,root=setup
    add_album(root,catalog,'合集',1);confirm(client,'合集')
    class MA:
        configured=True
        def sync_collections(self,*args,**kwargs): raise MAError('MA 认证失败，请检查 API token')
    app.state.collections.ma=MA()
    result=generate(client)
    assert result['generation']['status']=='done'
    assert result['snapshot']['items'][0]['title']=='合集'
    assert result['generation']['integration']['ma']['status']=='failed'
    assert '认证失败' in result['generation']['integration']['ma']['message']


def test_missing_ma_explicitly_reported_without_network(setup,monkeypatch):
    client,app,catalog,root=setup
    monkeypatch.delenv('KIDS_MA_URL',raising=False);monkeypatch.delenv('KIDS_MA_TOKEN',raising=False)
    add_album(root,catalog,'合集',1);confirm(client,'合集')
    result=generate(client)
    assert result['generation']['integration']['ma']['status']=='not_configured'


def test_ma_sync_runs_without_db_write_lock_and_rechecks_source(setup):
    client,app,catalog,root=setup
    add_album(root,catalog,'合集',1);confirm(client,'合集')
    class MA:
        configured=True
        def sync_collections(self, expected, **kwargs):
            assert expected['合集']['title']=='合集'
            # Both writes would block if MA ran while generation held DB locks.
            catalog.refresh([])
            with app.state.collections.db() as con:
                con.execute("update completions set status='incomplete' where folder='合集'")
            return {'status':'ready','message':'已核对'}
    app.state.collections.ma=MA()
    result=generate(client)
    assert result['generation']['integration']['ma']['status']=='failed'
    assert '变化' in result['generation']['integration']['ma']['message']


def test_stale_worker_cannot_overwrite_new_integration(setup):
    client,app,catalog,root=setup
    store=app.state.collections
    with store.db() as con:
        con.execute("update generation set token='new' where id=1")
    assert store.update_integration('old',{'phase':'syncing'}) is False
    assert store.read()['generation']['integration']!={'phase':'syncing'}


def test_ready_state_commits_before_final_catalog_guard_is_released(setup):
    from contextlib import contextmanager
    client,app,catalog,root=setup
    add_album(root,catalog,'合集',1);confirm(client,'合集')
    store=app.state.collections
    synced=False
    verified=[]
    original=store.candidate_source
    class MA:
        configured=True
        def sync_collections(self,*a,**kw):
            nonlocal synced
            synced=True
            return {'status':'ready','message':'已核对'}
    @contextmanager
    def observed_source():
        with original() as rows:
            yield rows
            if synced:
                state=store.read()['generation']
                verified.append(state['status']=='done' and state['integration']['ma']['status']=='ready')
                assert verified[-1], 'ready commit must remain inside final source guard'
    store.ma=MA();store.candidate_source=observed_source
    result=generate(client)
    assert verified==[True]
    assert result['generation']['integration']['ma']['status']=='ready'


def test_partial_tag_failure_retries_without_reconfirming_completion(setup,monkeypatch):
    import src.collection_metadata as metadata
    client,app,catalog,root=setup
    folder=add_album(root,catalog,'合集',2);confirm(client,'合集')
    real=metadata.write_missing
    calls=0
    def fail_second(path,changes):
        nonlocal calls
        calls+=1
        if calls==2: raise OSError('disk write interrupted')
        return real(path,changes)
    monkeypatch.setattr(metadata,'write_missing',fail_second)
    first=generate(client)
    assert first['generation']['integration']['tags_updated']==1
    assert first['generation']['integration']['metadata_errors']
    assert first['generation']['integration']['ma']['status']=='failed'
    monkeypatch.setattr(metadata,'write_missing',real)
    second=generate(client)
    assert second['generation']['status']=='done'
    assert second['generation']['integration']['tags_updated']==1
    assert second['generation']['integration']['metadata_errors']==[]
    assert all(read_tags(p)['album']==['合集'] for p in folder.iterdir())

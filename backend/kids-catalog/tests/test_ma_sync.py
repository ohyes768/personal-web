import pytest
from src.music_assistant import MAError
from src.ma_sync import synchronize


EXPECTED={'合集':{'title':'合集','files':['001-故事.mp3']}}


def track(path='合集/001-故事.mp3',album='library://album/1',provider='local1'):
    return {'album':{'name':'合集','uri':album},'provider_mappings':[
        {'item_id':path,'provider_instance':provider,'provider_domain':'filesystem_local','available':True}]}


class Client:
    root='/music'
    def __init__(self):
        self.calls=[];self.statuses=['running','success'];self.tracks=[track()]
    def call(self,command,**args):
        args.pop('request_timeout',None)
        self.calls.append((command,args))
        if command=='providers': return [{'domain':'filesystem_local','instance_id':'local1','available':True},
                                         {'domain':'spotify','instance_id':'stream','available':True}]
        if command=='config/providers/get': return {'values':{'path':{'value':'/music'}}}
        if command=='music/sync': return [{'id':'sync1','status':'pending'}]
        if command=='tasks/get': return {'id':'sync1','status':self.statuses.pop(0) if len(self.statuses)>1 else self.statuses[0]}
        raise AssertionError(command)
    def library_tracks(self,**kwargs): return self.tracks
    def album_tracks(self,uri,**kwargs): return self.tracks


def test_waits_for_tasks_and_matches_real_paths(monkeypatch):
    monkeypatch.setattr('src.ma_sync.time.sleep',lambda _:None)
    c=Client();events=[]
    assert synchronize(c,EXPECTED,progress=events.append)['status']=='ready'
    assert next(c for c in c.calls if c[0]=='music/sync')==('music/sync',{'providers':['local1'],'media_types':['track','album']})
    assert len([x for x in c.calls if x[0]=='tasks/get'])==2
    assert events[-1]['status']=='verifying'


@pytest.mark.parametrize('status',['failed','cancelled','partial_success','unknown'])
def test_non_successful_tasks_never_claim_ready(status):
    c=Client();c.statuses=[status]
    with pytest.raises(MAError): synchronize(c,EXPECTED)


def test_timeout_does_not_return_ready():
    c=Client();c.statuses=['running']
    with pytest.raises(MAError,match='超时'): synchronize(c,EXPECTED,timeout=0)


@pytest.mark.parametrize('bad_track', [track('其他合集/001-故事.mp3'),track(provider='spotify')])
def test_same_named_wrong_directory_or_source_is_not_ready(bad_track):
    c=Client();c.statuses=['success'];c.tracks=[bad_track]
    with pytest.raises(MAError,match='尚未'): synchronize(c,EXPECTED)


def test_stale_extra_track_in_album_is_not_ready():
    c=Client();c.statuses=['success'];c.tracks=[track(),track('合集/002-旧文件.mp3')]
    with pytest.raises(MAError,match='不一致'): synchronize(c,EXPECTED)


def test_empty_task_list_and_missing_provider_fail_explicitly():
    c=Client();c.call=lambda *a,**kw: []
    with pytest.raises(MAError,match='本地文件来源'): synchronize(c,EXPECTED)


def test_cancellation_checked_before_network():
    c=Client()
    with pytest.raises(MAError,match='过期'): synchronize(c,EXPECTED,cancelled=lambda:True)
    assert c.calls==[]


def test_foreign_only_extra_track_in_album_is_not_silently_ignored():
    c=Client();c.statuses=['success']
    c.album_tracks=lambda *a,**kw: [track(),track('foreign.mp3',provider='spotify')]
    with pytest.raises(MAError,match='不一致'): synchronize(c,EXPECTED)

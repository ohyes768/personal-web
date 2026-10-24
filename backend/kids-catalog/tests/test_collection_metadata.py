import json
import os
import shutil
from pathlib import Path

import pytest
from src.audio_tags import read_tags, write_missing
from src.collection_metadata import MetadataError, prepare_collection, recover_manifest

FIXTURES = Path(__file__).parent / 'fixtures'


def make(root, name='001-故事', ext='mp3'):
    p = root / '听，小蜗牛艾玛' / f'{name}.{ext}'
    p.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURES / f'tone.{ext}', p)
    return p


def manifest(folder):
    return [[p.name, p.stat().st_size, p.stat().st_mtime_ns] for p in sorted(folder.iterdir())]


@pytest.mark.parametrize('ext', ['mp3', 'm4a'])
def test_prepare_fill_only_checkpoint_and_idempotency(tmp_path, ext):
    root=tmp_path/'music'; p=make(root,ext=ext)
    before=manifest(p.parent); checkpoints=[]
    after, count=prepare_collection(root,p.parent.name,p.parent.name,before,tmp_path/'audit',checkpoints.append)
    assert count==1 and checkpoints==[after]
    assert read_tags(p)=={'album':[p.parent.name],'title':['故事'],'tracknumber':['1'],
                          'artist':['哆咪音频'],'albumartist':['哆咪音频']}
    assert prepare_collection(root,p.parent.name,p.parent.name,after,tmp_path/'audit',checkpoints.append)==(after,0)
    assert len(list((tmp_path/'audit').glob('*.jsonl')))==1


def test_existing_title_performer_and_manual_order_preserved(tmp_path):
    root=tmp_path/'music'; p=make(root,name='未编号')
    write_missing(p,{'album':[p.parent.name],'title':['原歌名'],'artist':['真实演唱者'],
                     'tracknumber':['7/76'],'albumartist':['原专辑艺术家']})
    before=p.read_bytes(); rows=manifest(p.parent)
    assert prepare_collection(root,p.parent.name,p.parent.name,rows,tmp_path/'audit',lambda x:None)==(rows,0)
    assert p.read_bytes()==before


@pytest.mark.parametrize('values', [{'album':['其他专辑']},{'tracknumber':['bad']}])
def test_conflicts_never_overwrite(tmp_path, values):
    root=tmp_path/'music'; p=make(root); write_missing(p,values); before=p.read_bytes()
    with pytest.raises(MetadataError):
        prepare_collection(root,p.parent.name,p.parent.name,manifest(p.parent),tmp_path/'audit',lambda x:None)
    assert p.read_bytes()==before


def test_unnumbered_missing_order_not_guessed(tmp_path):
    root=tmp_path/'music'; p=make(root,name='没有编号'); before=p.read_bytes()
    with pytest.raises(MetadataError,match='曲序'):
        prepare_collection(root,p.parent.name,p.parent.name,manifest(p.parent),tmp_path/'audit',lambda x:None)
    assert p.read_bytes()==before


def test_checkpoint_failure_can_recover_only_own_audited_changes(tmp_path):
    root=tmp_path/'music'; p=make(root); before=manifest(p.parent)
    def fail(rows): raise RuntimeError('checkpoint unavailable')
    with pytest.raises(RuntimeError):
        prepare_collection(root,p.parent.name,p.parent.name,before,tmp_path/'audit',fail)
    observed=manifest(p.parent)
    assert observed!=before
    assert recover_manifest(root,p.parent.name,before,observed,tmp_path/'audit')==observed
    stat=p.stat()
    os.utime(p,ns=(stat.st_atime_ns,stat.st_mtime_ns+1_000_000_000))
    with pytest.raises(MetadataError):
        recover_manifest(root,p.parent.name,before,manifest(p.parent),tmp_path/'audit')


def test_replace_failure_does_not_change_original_or_checkpoint(tmp_path,monkeypatch):
    root=tmp_path/'music'; p=make(root); before=p.read_bytes(); checkpoints=[]
    def fail(*args): raise OSError('replace denied')
    monkeypatch.setattr('src.collection_metadata.os.replace',fail)
    with pytest.raises(MetadataError):
        prepare_collection(root,p.parent.name,p.parent.name,manifest(p.parent),tmp_path/'audit',checkpoints.append)
    assert p.read_bytes()==before and checkpoints==[]
    assert not list(p.parent.glob('*.tagging-tmp'))


def test_entire_plan_validated_before_any_writes(tmp_path):
    root=tmp_path/'music'; p=make(root); q=make(root,name='002-另一首')
    write_missing(q,{'album':['冲突']}); before=p.read_bytes()
    with pytest.raises(MetadataError):
        prepare_collection(root,p.parent.name,p.parent.name,manifest(p.parent),tmp_path/'audit',lambda x:None)
    assert p.read_bytes()==before

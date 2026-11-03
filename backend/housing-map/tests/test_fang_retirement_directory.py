"""房天下退役后的目录/用途契约。

覆盖：
- 目录初始化不再导入旧房天下映射与候选（含损坏旧文件不阻断启动）
- 通用写入口拒绝新的房天下关联，历史读取与显式解绑仍可用
- 合并唯一性只看当前幸福里来源
- 用途证据只认透明售房网；房天下样本不参与判断
"""
import json
import sqlite3

import pytest

from src.services.community_directory import prepare_directory
from src.services.community_registry import CommunityRegistry
from src.services.residential_classifier import classify_sources


def seeded(tmp_path):
    (tmp_path / 'binjiang_communities.json').write_text(json.dumps([
        {'community_id': '100', 'community_name': '测试花园', 'district': '滨江',
         'address': '滨江区测试路1号'}]), encoding='utf-8')
    (tmp_path / 'property_types.json').write_text(json.dumps(
        {'100': {'property_type': '住宅'}}), encoding='utf-8')
    return prepare_directory(tmp_path)


def legacy_mapping_file(tmp_path):
    (tmp_path / 'rental_community_mappings.json').write_text(json.dumps({'version': 1, 'mappings': [
        {'source': 'fang', 'community_id': '100', 'source_community_id': '123',
         'source_name': '测试花园', 'status': 'verified'}]}), encoding='utf-8')


def legacy_mapping_db(tmp_path):
    db = tmp_path / 'rental_sources.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE mappings (payload TEXT)')
        conn.execute('CREATE TABLE candidates (community_id TEXT, payload TEXT, rejected INTEGER)')
        conn.execute('INSERT INTO mappings VALUES (?)', (json.dumps(
            {'source': 'fang', 'community_id': '100', 'source_community_id': '123',
             'source_name': '测试花园', 'status': 'verified'}),))
        conn.execute('INSERT INTO candidates VALUES (?, ?, 1)', ('100', json.dumps(
            {'source': 'fang', 'source_community_id': '456', 'source_name': '测试花园',
             'source_address': '滨江区测试路1号'}),))
    return db


def test_directory_init_ignores_legacy_fang_mapping_file(tmp_path):
    legacy_mapping_file(tmp_path)
    store = seeded(tmp_path)
    assert not [s for s in store.sources() if s['source'] == 'fang']
    assert store.communities()[0]['community_id'] == '100'
    # 旧文件仍被备份，但不作为当前来源。
    assert (tmp_path / 'directory-backup' / 'rental_community_mappings.json').exists()


def test_directory_init_ignores_legacy_fang_mapping_database(tmp_path):
    legacy_mapping_db(tmp_path)
    store = seeded(tmp_path)
    assert not [s for s in store.sources() if s['source'] == 'fang']
    assert store.communities()[0]['community_id'] == '100'
    assert (tmp_path / 'directory-backup' / 'rental_sources.sqlite3').exists()


def test_corrupt_legacy_fang_files_do_not_block_directory_init(tmp_path):
    legacy_mapping_file(tmp_path)
    (tmp_path / 'rental_sources.sqlite3').write_bytes(b'not a database at all')
    store = seeded(tmp_path)
    assert not [s for s in store.sources() if s['source'] == 'fang']
    assert store.communities()[0]['community_id'] == '100'


def test_empty_directory_initializes_without_fang_sources(tmp_path):
    store = prepare_directory(tmp_path)
    assert store.sources() == []
    assert store.communities() == []


def test_registry_rejects_new_fang_association_but_keeps_history_readable(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    store.create('测试花园', district='滨江', address='测试路1号', community_id='c1')
    item = store.ingest(dict(source='fang', source_kind='community', source_id='f1',
                             name='测试花园', district='滨江', address='测试路1号'))
    with pytest.raises(ValueError, match='房天下'):
        store.associate(item['id'], 'c1')
    assert store.sources()[0]['status'] == 'pending'
    assert store.sources()[0]['community_id'] is None
    # 历史记录仍可读取。
    assert store.sources()[0]['source'] == 'fang'
    assert not [e for e in store.events('c1') if e['action'] == 'associate']


def test_registry_create_from_source_rejects_fang(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    item = store.ingest(dict(source='fang', source_kind='community', source_id='f1',
                             name='测试花园', district='滨江'))
    with pytest.raises(ValueError, match='房天下'):
        store.create_from_source(item['id'], name='测试花园', aliases=[], district='滨江', address='测试路1号')
    assert store.communities() == []


def test_explicit_unlink_and_ignore_still_work_for_fang(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    store.create('测试花园', district='滨江', address='测试路1号', community_id='c1')
    item = store.ingest(dict(source='fang', source_kind='community', source_id='f1',
                             name='测试花园', district='滨江'))
    store.unlink(item['id'])
    assert store.sources()[0]['status'] == 'pending'
    store.ignore_source(item['id'], '历史来源')
    assert store.sources()[0]['status'] == 'ignored'
    assert store.is_ignored('fang', 'community', 'f1')


def test_merge_uniqueness_only_counts_current_xingfuli_source(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    store.create('甲', district='滨江', address='测试路1号', community_id='c1')
    store.create('乙', district='滨江', address='测试路2号', community_id='c2')
    # 两侧各有一个历史房天下来源，不阻塞当前合并。
    for cid, sid in (('c1', 'f1'), ('c2', 'f2')):
        row = store.ingest(dict(source='fang', source_kind='community', source_id=sid,
                                name='测试花园', district='滨江'))
        with store.db() as db:
            db.execute("UPDATE sources SET cid=?,status='matched' WHERE id=?", (cid, row['id']))
    store.merge('c1', 'c2')
    assert store.resolve('c1') == 'c2'


def test_merge_still_blocks_two_current_xingfuli_sources(tmp_path):
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    store.create('甲', district='滨江', address='测试路1号', community_id='c1')
    store.create('乙', district='滨江', address='测试路2号', community_id='c2')
    for cid, sid in (('c1', 'x1'), ('c2', 'x2')):
        row = store.ingest(dict(source='xingfuli', source_kind='community', source_id=sid,
                                name='测试花园', district='滨江'))
        with store.db() as db:
            db.execute("UPDATE sources SET cid=?,status='matched' WHERE id=?", (cid, row['id']))
    with pytest.raises(ValueError, match='租金来源'):
        store.merge('c1', 'c2')


def test_fang_samples_are_not_residential_use_evidence():
    tmsf = dict(source='tmsf', source_id='1', property_type='住宅')
    assert classify_sources([tmsf]) == 'residential'
    # 历史房天下样本既不能证明住宅，也不能否决透明售房网的住宅证据。
    assert classify_sources([tmsf, dict(source='fang', samples=[{'property_type': '写字楼'}])]) == 'residential'
    # 只有房天下样本时保持待核对，不会凭空成为住宅。
    assert classify_sources([dict(source='fang', samples=[{'property_type': '住宅'}])]) == 'pending'


def test_manual_admission_and_review_payloads_survive_retirement(tmp_path):
    store = seeded(tmp_path)
    admission = store.decide_admission('100', 'exclude', revision=1, reason='人工保留排除')
    assert admission['state'] == 'excluded' and admission['auto_review_locked']
    with store.db() as db:
        db.execute('INSERT OR IGNORE INTO rejected VALUES (?,?)', ('tmsf-100', '100'))
    before = store.admission('100'), store.events('100')
    restarted = prepare_directory(tmp_path)
    assert restarted.admission('100') == before[0]
    assert restarted.events('100') == before[1]
    with restarted.db() as db:
        assert db.execute('SELECT COUNT(*) FROM rejected').fetchone()[0] == 1

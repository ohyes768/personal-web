"""Real MP3/M4A metadata, safe publication and recovery tests."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import mutagen
import pytest

from src.tag_audio import run
from src.tag_files import restore

FIXTURES = Path(__file__).parent / 'fixtures'


def make_audio(root, ext='mp3', name='001-小兔子乖乖'):
    p = root / '宝宝巴士' / f'{name}.{ext}'
    p.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURES / f'tone.{ext}', p)
    return p


def tags(p):
    return mutagen.File(p, easy=True)


def set_tags(p, **values):
    audio = tags(p)
    if audio.tags is None:
        audio.add_tags()
    for k, v in values.items():
        audio[k] = [v]
    audio.save()


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.parametrize('ext', ['mp3', 'm4a'])
def test_preview_apply_idempotency_and_exact_restore(tmp_path, ext):
    root = tmp_path / 'music'
    p = make_audio(root, ext)
    before = p.read_bytes()
    mtime = p.stat().st_mtime_ns
    result = run(root)
    assert result['files'][0]['status'] == 'needs_change'
    assert p.read_bytes() == before and p.stat().st_mtime_ns == mtime
    assert result['run_dir'] is None
    applied = run(root, apply=True, backup_dir=tmp_path / 'backup')
    assert applied['files'][0]['status'] == 'applied'
    audio = tags(p)
    assert audio['album'] == ['宝宝巴士']
    assert audio['title'] == ['小兔子乖乖']
    assert audio['tracknumber'] == ['1']
    assert audio['albumartist'] == ['哆咪音频']
    assert audio['artist'] == ['哆咪音频']
    assert run(root, apply=True, backup_dir=tmp_path / 'backup')['run_dir'] is None
    assert run(root)['files'][0]['status'] == 'unchanged'
    restored = restore(root, Path(applied['run_dir']))
    assert restored[0]['status'] == 'restored'
    assert p.read_bytes() == before
    assert restore(root, Path(applied['run_dir']))[0]['status'] == 'already_restored'


@pytest.mark.parametrize('ext', ['mp3', 'm4a'])
def test_existing_fields_preserved_and_album_artist_reused(tmp_path, ext):
    root = tmp_path / 'music'
    p = make_audio(root, ext)
    set_tags(p, artist='宝宝巴士', albumartist='宝宝巴士', genre='儿童', tracknumber='1/20')
    run(root, apply=True, backup_dir=tmp_path / 'backup')
    audio = tags(p)
    assert audio['genre'] == ['儿童']
    assert audio['tracknumber'] == ['1/20']
    assert audio['albumartist'] == ['宝宝巴士']


def test_conflict_skips_entire_file_and_reports_current_value(tmp_path):
    root = tmp_path / 'music'
    p = make_audio(root)
    set_tags(p, album='原有专辑')
    before = p.read_bytes()
    row = run(root, apply=True, backup_dir=tmp_path / 'backup')['files'][0]
    assert row['status'] == 'conflict'
    assert row['current']['album'] == ['原有专辑']
    assert 'album' in row['conflicts']
    assert p.read_bytes() == before
    assert not (tmp_path / 'backup').exists()


def test_duplicate_numbers_and_ambiguous_album_artists_skip_album(tmp_path):
    root = tmp_path / 'music'
    p = make_audio(root)
    q = make_audio(root, name='001-另一首')
    assert all(r['status'] == 'conflict' for r in run(root)['files'])
    q.rename(q.with_name('002-另一首.mp3'))
    q = q.with_name('002-另一首.mp3')
    set_tags(p, albumartist='甲')
    set_tags(q, albumartist='乙')
    assert all(r['status'] == 'conflict' for r in run(root)['files'])


def test_bad_files_parts_and_album_filter(tmp_path):
    root = tmp_path / 'music'
    p = make_audio(root)
    (p.parent / '002-损坏.mp3').write_bytes(b'not audio')
    (p.parent / '003-未完成.mp3.part').write_bytes(b'partial')
    make_audio(root, name='没有编号')
    other = root / '其他合集'
    other.mkdir()
    shutil.copy2(FIXTURES / 'tone.mp3', other / '001-其他.mp3')
    result = run(root, album='宝宝巴士')
    assert len(result['files']) == 3
    assert {r['status'] for r in result['files']} == {'needs_change', 'error', 'skipped'}
    with pytest.raises(ValueError):
        run(root, album='../outside')
    with pytest.raises(ValueError):
        run(root, album='不存在')


def test_backup_must_be_outside_scanned_root(tmp_path):
    root = tmp_path / 'music'
    p = make_audio(root)
    original = digest(p)
    with pytest.raises(ValueError):
        run(root, apply=True, backup_dir=root / 'backup')
    assert digest(p) == original


def test_restore_protects_later_edits_and_corrupt_backup(tmp_path):
    root = tmp_path / 'music'
    p = make_audio(root)
    result = run(root, apply=True, backup_dir=tmp_path / 'backup')
    run_dir = Path(result['run_dir'])
    after = p.read_bytes()
    set_tags(p, title='后来人工修改')
    assert restore(root, run_dir)[0]['status'] == 'error'
    p.write_bytes(after)
    entry = json.loads((run_dir / 'manifest.jsonl').read_text(encoding='utf-8').splitlines()[0])
    (run_dir / entry['backup']).write_bytes(b'bad backup')
    assert restore(root, run_dir)[0]['status'] == 'error'
    assert p.read_bytes() == after


def test_publication_failure_keeps_original_and_removes_temp(tmp_path, monkeypatch):
    root = tmp_path / 'music'
    p = make_audio(root)
    before = p.read_bytes()
    def fail(*args):
        raise OSError('simulated replace failure')
    monkeypatch.setattr('src.tag_files.os.replace', fail)
    row = run(root, apply=True, backup_dir=tmp_path / 'backup')['files'][0]
    assert row['status'] == 'error'
    assert p.read_bytes() == before
    assert not list(p.parent.glob('*.tagging-tmp'))


@pytest.mark.parametrize('ext', ['mp3', 'm4a'])
def test_encoded_packets_unchanged(tmp_path, ext):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg required only for encoded-packet verification')
    root = tmp_path / 'music'
    p = make_audio(root, ext)
    def packet_hash():
        return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(p),
            '-map', '0:a:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'])
    before = packet_hash()
    assert run(root, apply=True, backup_dir=tmp_path / 'backup')['files'][0]['status'] == 'applied'
    assert packet_hash() == before


def test_restore_rejects_path_traversal(tmp_path):
    root = tmp_path / 'music'
    make_audio(root)
    result = run(root, apply=True, backup_dir=tmp_path / 'backup')
    run_dir = Path(result['run_dir'])
    manifest = run_dir / 'manifest.jsonl'
    entry = json.loads(manifest.read_text(encoding='utf-8').splitlines()[0])
    entry['path'] = '../outside.mp3'
    manifest.write_text(json.dumps(entry) + '\n', encoding='utf-8')
    assert restore(root, run_dir)[0]['status'] == 'error'


def test_album_artist_consistent_across_tracks(tmp_path):
    root = tmp_path / 'music'
    p = make_audio(root)
    q = make_audio(root, 'm4a', name='002-第二首')
    set_tags(p, artist='创作者', albumartist='创作者')
    result = run(root, apply=True, backup_dir=tmp_path / 'backup')
    assert result['summary'] == {'applied': 2}
    assert tags(q)['albumartist'] == ['创作者']
    assert tags(q)['tracknumber'] == ['2']


def test_backup_failure_never_changes_original(tmp_path, monkeypatch):
    root = tmp_path / 'music'
    p = make_audio(root)
    before = p.read_bytes()
    real_copy = shutil.copy2
    def fail_backup(source, dest, *args, **kwargs):
        if str(dest).endswith('.bak'):
            raise OSError('disk full')
        return real_copy(source, dest, *args, **kwargs)
    monkeypatch.setattr('src.tag_files.shutil.copy2', fail_backup)
    result = run(root, apply=True, backup_dir=tmp_path / 'backup')
    assert result['files'][0]['status'] == 'error'
    assert p.read_bytes() == before
    assert not list(p.parent.glob('*.tagging-tmp'))


def test_cli_preview_apply_and_restore(tmp_path, capsys):
    from src.tag_audio import main
    root = tmp_path / 'music'
    p = make_audio(root)
    before = p.read_bytes()
    assert main(['--root', str(root), '--album', '宝宝巴士']) == 0
    assert json.loads(capsys.readouterr().out)['mode'] == 'preview'
    assert p.read_bytes() == before
    assert main(['--root', str(root), '--apply', '--backup-dir', str(tmp_path / 'backup')]) == 0
    run_dir = json.loads(capsys.readouterr().out)['run_dir']
    assert main(['--root', str(root), '--restore', run_dir]) == 0
    capsys.readouterr()
    assert p.read_bytes() == before
    with pytest.raises(SystemExit):
        main(['--root', str(root), '--apply'])


@pytest.mark.requires_symlink
def test_symlinked_audio_never_modified(tmp_path):
    root = tmp_path / 'music'
    p = make_audio(root)
    outside = tmp_path / 'outside.mp3'
    shutil.copy2(p, outside)
    link = p.parent / '002-link.mp3'
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip('symlink privilege unavailable')
    before = outside.read_bytes()
    result = run(root, apply=True, backup_dir=tmp_path / 'backup')
    assert next(r for r in result['files'] if r['path'].endswith('002-link.mp3'))['status'] == 'error'
    assert outside.read_bytes() == before


def test_stale_plan_does_not_overwrite_external_edits(tmp_path):
    from src.audio_tags import scan
    from src.tag_files import apply_rows
    root = tmp_path / 'music'
    p = make_audio(root)
    rows = scan(root)
    set_tags(p, title='稍后人工编辑')
    before = p.read_bytes()
    assert apply_rows(root, rows, tmp_path / 'backup') is None
    assert rows[0]['status'] == 'error'
    assert p.read_bytes() == before


def test_artist_consistency_includes_valid_unnumbered_audio(tmp_path):
    root = tmp_path / 'music'
    p = make_audio(root)
    q = make_audio(root, name='没有编号')
    set_tags(q, albumartist='已有创作者')
    result = run(root)
    numbered = next(r for r in result['files'] if r['path'].endswith('001-小兔子乖乖.mp3'))
    assert numbered['proposed']['albumartist'] == ['已有创作者']
    set_tags(p, albumartist='另一位')
    result = run(root)
    numbered = next(r for r in result['files'] if r['path'].endswith('001-小兔子乖乖.mp3'))
    assert numbered['status'] == 'conflict'


def test_backup_directory_sync_failure_does_not_publish(tmp_path, monkeypatch):
    root = tmp_path / 'music'
    p = make_audio(root)
    before = p.read_bytes()
    def fail(path):
        raise OSError('directory fsync failed')
    monkeypatch.setattr('src.tag_files.sync_directory', fail, raising=False)
    result = run(root, apply=True, backup_dir=tmp_path / 'backup')
    assert result['files'][0]['status'] == 'error'
    assert p.read_bytes() == before


def test_duplicate_number_in_corrupt_file_blocks_album(tmp_path):
    root = tmp_path / 'music'
    p = make_audio(root)
    (p.parent / '001-损坏.mp3').write_bytes(b'broken')
    before = p.read_bytes()
    result = run(root, apply=True, backup_dir=tmp_path / 'backup')
    row = next(r for r in result['files'] if r['path'].endswith('001-小兔子乖乖.mp3'))
    assert row['status'] == 'conflict'
    assert p.read_bytes() == before

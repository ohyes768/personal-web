"""Version provenance and cache separation without real Hermes calls."""
import json

import pytest

from tests.test_quality_service import fake_output, run_service, stock
from src.services.quality_service import parse_quality_output


def test_reported_version_survives_score_storage(tmp_path):
    raw = json.loads(fake_output('000001', '样本'))
    raw['skill_version'] = '4.3.0'
    service, job = run_service(tmp_path, ['000001'], {'000001': stock()},
                               lambda *args: 'run', lambda *args: json.dumps(raw))
    assert job['status'] == 'succeeded'
    assert service.get_all()['000001']['skill_version'] == '4.3.0'


def test_legacy_output_remains_unknown():
    score = parse_quality_output(fake_output('000001', '样本'), '000001', '样本')
    assert score.skill_version is None


@pytest.mark.parametrize('version', ['', 'latest', 4, '4.3.0\nforged'])
def test_invalid_reported_version_rejected(version):
    raw = json.loads(fake_output('000001', '样本'))
    raw['skill_version'] = version
    with pytest.raises(ValueError):
        parse_quality_output(json.dumps(raw), '000001', '样本')


def test_deployed_manifest_is_read_fresh(tmp_path, monkeypatch):
    from src.services.quality_version import current_quality_skill_version
    path = tmp_path / 'SKILL.md'
    monkeypatch.delenv('HERMES_QUALITY_SKILL_VERSION', raising=False)
    monkeypatch.setenv('HERMES_QUALITY_SKILL_PATH', str(path))
    assert current_quality_skill_version() is None
    path.write_text('---\nmetadata:\n  version: 4.3.0\n---\n# skill', encoding='utf-8')
    assert current_quality_skill_version() == '4.3.0'
    path.write_text('---\nmetadata:\n  version: 4.4.0\n---\n', encoding='utf-8')
    assert current_quality_skill_version() == '4.4.0'


def test_version_changes_separate_runs_and_mismatch_does_not_overwrite(tmp_path, monkeypatch):
    keys, prompts = [], []
    def submit(cfg, prompt, key):
        keys.append(key)
        prompts.append(prompt)
        return 'run'
    def poll(*args):
        raw = json.loads(fake_output('000001', '样本'))
        raw['skill_version'] = '4.3.0'
        return json.dumps(raw)
    monkeypatch.setenv('HERMES_QUALITY_SKILL_VERSION', '4.3.0')
    service, first = run_service(tmp_path, ['000001'], {'000001': stock()}, submit, poll)
    assert first['status'] == 'succeeded'
    monkeypatch.setenv('HERMES_QUALITY_SKILL_VERSION', '4.4.0')
    _, second = run_service(tmp_path, ['000001'], {'000001': stock()}, submit, poll)
    assert keys[0] != keys[1]
    assert '4.3.0' in keys[0] and '4.4.0' in keys[1]
    assert '4.4.0' in prompts[1]
    assert second['status'] == 'failed'
    assert service.get_all()['000001']['skill_version'] == '4.3.0'


def test_unknown_current_version_explicit_reanalysis_avoids_old_cached_run(tmp_path, monkeypatch):
    monkeypatch.delenv('HERMES_QUALITY_SKILL_VERSION', raising=False)
    monkeypatch.delenv('HERMES_QUALITY_SKILL_PATH', raising=False)
    keys = []
    def submit(cfg, prompt, key):
        keys.append(key)
        return 'run'
    for _ in range(2):
        run_service(tmp_path, ['000001'], {'000001': stock()}, submit,
                    lambda *args: fake_output('000001', '样本'))
    assert keys[0] != keys[1]

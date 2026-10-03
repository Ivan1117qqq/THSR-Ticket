import json

import pytest

from thsr_ticket.config_store import ConfigVersionError, read_config_data, write_config_data


def test_legacy_read_is_readonly_and_first_save_backs_up_exact_bytes(tmp_path):
    path = tmp_path / 'booking.local.json'
    original = b'\xef\xbb\xbf{ "adult_tickets": 1 }\r\n'
    path.write_bytes(original)
    state = tmp_path / 'booking.local.state.json'
    state.write_text('pending marker')
    assert read_config_data(path) == {'adult_tickets': 1}
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('*.config-backups'))
    write_config_data(path, {'adult_tickets': 2})
    backups = list((tmp_path / 'booking.local.json.config-backups').glob('*.json'))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert json.loads(path.read_text())['_schema_version'] == 1
    assert read_config_data(path) == {'adult_tickets': 2}
    write_config_data(path, {'adult_tickets': 3})
    assert len(list(backups[0].parent.glob('*.json'))) == 1
    assert state.read_text() == 'pending marker'


@pytest.mark.parametrize('version', [2, 0, -1, True, '1', 1.0, None, {}, []])
def test_unsupported_versions_cannot_be_read_or_overwritten(tmp_path, version):
    path = tmp_path / 'config.json'
    original = json.dumps({'_schema_version': version, 'personal_id': 'PRIVATE'})
    path.write_text(original)
    with pytest.raises(ConfigVersionError):
        read_config_data(path)
    with pytest.raises(ConfigVersionError):
        write_config_data(path, {'adult_tickets': 1})
    assert path.read_text() == original
    assert not list(tmp_path.glob('*.config-backups'))


def test_backup_failure_prevents_migration(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"adult_tickets": 1}')
    (tmp_path / 'config.json.config-backups').write_text('not a directory')
    with pytest.raises(OSError):
        write_config_data(path, {'adult_tickets': 2})
    assert path.read_text() == '{"adult_tickets": 1}'


def test_atomic_write_failure_keeps_original_and_backup(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    original = '{"adult_tickets": 1}'
    path.write_text(original)

    def fail(*args):
        raise OSError('disk failure')

    monkeypatch.setattr('thsr_ticket.config_store.atomic_json', fail)
    with pytest.raises(OSError):
        write_config_data(path, {'adult_tickets': 2})
    assert path.read_text() == original
    assert next((tmp_path / 'config.json.config-backups').glob('*.json')).read_text() == original


def test_corrupt_destination_cannot_be_overwritten(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('broken')
    with pytest.raises(ValueError):
        write_config_data(path, {})
    assert path.read_text() == 'broken'

import hashlib
import json
import os
import stat
import threading
import zipfile
from pathlib import Path

import pytest

from thsr_ticket import backup
from thsr_ticket.config_store import RESTORE_MARKER, ConfigRestoreError, read_config_data, write_config_data
from thsr_ticket.record_lock import record_lock, RecordBusy
from thsr_ticket.scan_report import ScanCancelled
from thsr_ticket.storage_errors import StorageError
from thsr_ticket.task_status import booking_guard
from thsr_ticket.unittest.test_gui import values
from thsr_ticket.application import form_config


def fixture_files(root, state=True):
    root.mkdir(parents=True, exist_ok=True)
    config = root / 'original.json'
    config.write_text(form_config(values()).json(), encoding='utf-8')
    if state:
        config.with_suffix('.state.json').write_bytes(b'{"status":"submission_pending","private":"FAKE"}')
    config.with_suffix('.task.json').write_bytes(b'{"version":1,"code":"running","query_only":false}')
    files = {
        'original.runs/' + 'a' * 32 + '/events.jsonl': b'{"event":"run_finished"}\n',
        'original.runs/' + 'a' * 32 + '/result.json': b'{"tickets":[{"id":"FAKE-CODE"}]}',
        'original.runs/archives/FAKE-CODE/state.json': b'{"status":"booked"}',
        'original.runs.history-backups/' + 'b' * 32 + '/' + 'c' * 32 + '/events.jsonl': b'broken legacy bytes',
        'original.runs.operations/' + 'd' * 32 + '.json': b'{"status":"pending"}',
        'original.json.config-backups/' + 'e' * 32 + '.json': b'{"personal_id":"FAKE-PRIVATE"}',
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return config


def bundle(tmp_path, state=True):
    config = fixture_files(tmp_path / 'source', state)
    plan = backup.preview_source(config)
    archive = tmp_path / 'saved.thsr-backup.zip'
    backup.export_backup(plan, archive)
    return config, plan, archive


def custom_archive(path, entries, mutate=None):
    manifest = {'format': 'travel-desk-backup', 'version': 1, 'app_version': '0.4.0',
                'created_at': '2026-10-23T12:00:00+08:00',
                'files': [{'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                           'mtime_ns': 1720000000000000000}
                          for name, data in entries]}
    if mutate:
        mutate(manifest)
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in entries:
            archive.writestr(name, data)
        archive.writestr('manifest.json', json.dumps(manifest))
    return path


def test_round_trip_all_groups_preserves_bytes_and_guard(tmp_path):
    config, plan, archive = bundle(tmp_path)
    assert plan['summary']['files'] == 9
    assert plan['summary']['has_state']
    assert 'FAKE' not in json.dumps(plan['summary'])
    original = {name: item['path'].read_bytes() for name, item in plan['items'].items()}
    preview = backup.preview_archive(archive, tmp_path / 'restored')
    restored = backup.restore_backup(preview)
    assert restored.name == 'booking.local.json'
    for name, content in original.items():
        assert (restored.parent / backup.restored_name(name)).read_bytes() == content
        assert (restored.parent / backup.restored_name(name)).stat().st_mtime_ns == plan['items'][name]['token'][1]
        assert plan['items'][name]['path'].read_bytes() == content
    assert booking_guard(config) == booking_guard(restored) == 'pending'
    assert not (restored.parent / RESTORE_MARKER).exists()
    assert read_config_data(restored) == read_config_data(config)


def test_restore_without_state_adds_review_guard(tmp_path):
    _, _, archive = bundle(tmp_path, state=False)
    plan = backup.preview_archive(archive, tmp_path / 'new')
    assert not plan['summary']['has_state']
    restored = backup.restore_backup(plan)
    assert booking_guard(restored) == 'pending'
    state = json.loads(restored.with_suffix('.state.json').read_text())
    assert state['restored_without_state'] is True


def test_existing_booked_or_damaged_state_is_never_replaced(tmp_path):
    for number, content in enumerate((b'{"status":"booked","booking_codes":["FAKE"]}', b'broken')):
        area = tmp_path / str(number)
        area.mkdir()
        config = fixture_files(area / 'source')
        config.with_suffix('.state.json').write_bytes(content)
        archive = area / 'copy.thsr-backup.zip'
        backup.export_backup(backup.preview_source(config), archive)
        restored = backup.restore_backup(backup.preview_archive(archive, area / 'target'))
        assert restored.with_suffix('.state.json').read_bytes() == content
        assert booking_guard(restored) in ('booked', 'unreadable')


def test_destination_conflicts_and_changed_archive_leave_original_untouched(tmp_path):
    config, _, archive = bundle(tmp_path)
    original = config.with_suffix('.state.json').read_bytes()
    target = tmp_path / 'target'
    plan = backup.preview_archive(archive, target)
    target.mkdir()
    marker = target / 'keep.txt'
    marker.write_text('keep')
    with pytest.raises(StorageError, match='backup_destination_exists'):
        backup.restore_backup(plan)
    assert marker.read_text() == 'keep'
    assert config.with_suffix('.state.json').read_bytes() == original
    plan = backup.preview_archive(archive, tmp_path / 'another')
    with archive.open('ab') as handle:
        handle.write(b'changed after preview')
    with pytest.raises(StorageError, match='backup_source_changed'):
        backup.restore_backup(plan)
    assert not (tmp_path / 'another').exists()


def test_export_revalidates_bytes_even_if_size_and_mtime_match(tmp_path):
    config = fixture_files(tmp_path / 'source')
    plan = backup.preview_source(config)
    state = config.with_suffix('.state.json')
    token = state.stat()
    state.write_bytes(state.read_bytes().replace(b'FAKE', b'EDIT'))
    os.utime(state, ns=(token.st_atime_ns, token.st_mtime_ns))
    target = tmp_path / 'new.thsr-backup.zip'
    with pytest.raises(StorageError, match='backup_source_changed'):
        backup.export_backup(plan, target)
    assert not target.exists()
    assert not list(tmp_path.glob('.thsr-backup-*'))


def test_export_never_overwrites_existing_archive(tmp_path):
    config, plan, archive = bundle(tmp_path)
    original = archive.read_bytes()
    with pytest.raises(StorageError, match='backup_destination_exists'):
        backup.export_backup(plan, archive)
    assert archive.read_bytes() == original and config.exists()


@pytest.mark.parametrize('name', [
    '../escape.json', '/config.json', 'C:/escape.json', 'runs/../escape.json', 'runs/CON.json',
    'runs/a\\b.json', 'runs/entry.json:stream', 'runs/trailing./file.json',
])
def test_archive_paths_are_rejected_before_any_restore_write(tmp_path, name):
    archive = custom_archive(tmp_path / 'bad.zip', [('config.json', b'{}'), (name, b'{}')])
    with pytest.raises(StorageError, match='backup_invalid'):
        backup.preview_archive(archive, tmp_path / 'restore')
    assert not (tmp_path / 'restore').exists()


@pytest.mark.parametrize('mutation', [
    lambda value: value.update(version=2),
    lambda value: value.update(version=True),
    lambda value: value['files'][0].update(sha256='0' * 64),
    lambda value: value['files'][0].update(bytes=True),
    lambda value: value['files'].append(dict(value['files'][0])),
])
def test_future_versions_bad_hashes_and_duplicate_members_are_rejected(tmp_path, mutation):
    path = custom_archive(tmp_path / 'bad.zip', [('config.json', b'{}')], mutation)
    with pytest.raises(StorageError, match='backup_invalid'):
        backup.preview_archive(path)


def test_symlinks_case_collisions_and_file_directory_conflicts_are_rejected(tmp_path):
    for index, names in enumerate((['runs/A.json', 'runs/a.json'], ['runs/a.json', 'runs/a.json/x.json'])):
        entries = [('config.json', b'{}'), *[(name, b'{}') for name in names]]
        path = custom_archive(tmp_path / f'bad-{index}.zip', entries)
        with pytest.raises(StorageError, match='backup_invalid'):
            backup.preview_archive(path)
    path = tmp_path / 'link.zip'
    custom_archive(path, [('config.json', b'{}')])
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo('config.json')
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        # validate the central-directory attributes without extracting anything.
        with pytest.raises(StorageError, match='backup_invalid'):
            backup.validate_manifest(archive)


def test_cancel_limits_and_source_links_fail_closed(tmp_path, monkeypatch):
    config = fixture_files(tmp_path / 'source')
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ScanCancelled):
        backup.preview_source(config, cancel)
    with monkeypatch.context() as patch:
        patch.setattr(backup, 'MAX_TOTAL', 1)
        with pytest.raises(StorageError, match='backup_limit'):
            backup.preview_source(config)
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == config.parent or original(path))
    with pytest.raises(StorageError, match='unsafe_path'):
        backup.preview_source(config)


def test_source_operation_lock_is_respected(tmp_path):
    config = fixture_files(tmp_path / 'source')
    with record_lock(config.with_suffix('.state.json')):
        with pytest.raises(RecordBusy):
            backup.preview_source(config)


def test_interrupted_restore_keeps_guard_and_blocks_config_loading(tmp_path, monkeypatch):
    class Interrupted(BaseException):
        pass
    _, _, archive = bundle(tmp_path, state=False)
    plan = backup.preview_archive(archive, tmp_path / 'partial')
    original = backup.transfer

    def interrupt(source, destination=None, **kwargs):
        if destination is not None and str(getattr(destination, 'name', '')).endswith('result.json'):
            raise Interrupted()
        return original(source, destination, **kwargs)

    monkeypatch.setattr(backup, 'transfer', interrupt)
    with pytest.raises(Interrupted):
        backup.restore_backup(plan)
    config = tmp_path / 'partial/booking.local.json'
    assert config.with_suffix('.state.json').exists()
    assert (config.parent / RESTORE_MARKER).exists()
    assert not config.exists()
    with pytest.raises(ConfigRestoreError):
        read_config_data(config)
    with pytest.raises(ConfigRestoreError):
        write_config_data(config, {})


def test_protected_config_is_not_decrypted_or_silently_converted(tmp_path):
    config = fixture_files(tmp_path / 'source')
    config.write_text(json.dumps({'personal_id': {'protection': 'windows-dpapi', 'value': 'FAKE-OPAQUE'}}))
    archive = tmp_path / 'protected.thsr-backup.zip'
    source = backup.preview_source(config)
    assert source['summary']['protection'] == 'windows-dpapi'
    backup.export_backup(source, archive)
    plan = backup.preview_archive(archive, tmp_path / 'restored')
    restored = backup.restore_backup(plan)
    assert restored.read_bytes() == config.read_bytes()


def test_state_appearing_after_preview_is_not_omitted(tmp_path):
    config = fixture_files(tmp_path / 'source', state=False)
    plan = backup.preview_source(config)
    config.with_suffix('.state.json').write_bytes(b'{"status":"submission_pending"}')
    target = tmp_path / 'saved.thsr-backup.zip'
    with pytest.raises(StorageError, match='backup_source_changed'):
        backup.export_backup(plan, target)
    assert not target.exists()
    assert booking_guard(config) == 'pending'


def test_destination_created_during_export_is_never_overwritten(tmp_path, monkeypatch):
    config = fixture_files(tmp_path / 'source')
    plan = backup.preview_source(config)
    target = tmp_path / 'race.thsr-backup.zip'
    original = Path.open

    def occupied(path, mode='r', *args, **kwargs):
        if path == target and mode == 'xb':
            with original(path, 'wb') as handle:
                handle.write(b'external file')
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', occupied)
    with pytest.raises(StorageError, match='backup_destination_exists'):
        backup.export_backup(plan, target)
    assert target.read_bytes() == b'external file'


def test_export_copy_failure_removes_own_partial_file_only(tmp_path, monkeypatch):
    config = fixture_files(tmp_path / 'source')
    plan = backup.preview_source(config)
    target = tmp_path / 'failed.thsr-backup.zip'
    original = Path.open

    def fail(path, mode='r', *args, **kwargs):
        if path.name.startswith('.thsr-backup-') and mode == 'rb':
            raise PermissionError('PRIVATE')
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', fail)
    with pytest.raises(PermissionError):
        backup.export_backup(plan, target)
    assert not target.exists()
    assert not list(tmp_path.glob('.thsr-backup-*'))
    assert booking_guard(config) == 'pending'

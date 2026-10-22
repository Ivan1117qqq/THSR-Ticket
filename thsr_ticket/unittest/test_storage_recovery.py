import errno
import json
from pathlib import Path

import pytest

from thsr_ticket.booking_records import record_paths
from thsr_ticket.record_lock import RecordBusy
from thsr_ticket.record_storage import inventory, move_history, restore_history, backup_batches
from thsr_ticket.storage_errors import StorageError, error_info
from thsr_ticket.storage_journal import pending_operations, recover_operation


class ProcessInterrupted(BaseException):
    """Simulates a killed process, bypassing in-process exception rollback."""


def records(tmp_path):
    config = tmp_path / 'booking.json'
    state, runs = record_paths(config)
    for identifier in ('a' * 32, 'b' * 32):
        directory = runs / identifier
        directory.mkdir(parents=True)
        (directory / 'events.jsonl').write_bytes(b'{"event":"run_finished"}\n')
    return config, state, runs


def interrupt_rename(monkeypatch, number):
    original = Path.rename
    calls = []

    def rename(source, target):
        if source.is_dir() and len(source.name) == 32:
            calls.append(source)
            if len(calls) == number:
                raise ProcessInterrupted()
        return original(source, target)

    monkeypatch.setattr(Path, 'rename', rename)


@pytest.mark.parametrize('number', [1, 2])
def test_interrupted_move_can_recover_after_restart(tmp_path, monkeypatch, number):
    config, state, runs = records(tmp_path)
    original = inventory(config)
    with monkeypatch.context() as patch:
        interrupt_rename(patch, number)
        with pytest.raises(ProcessInterrupted):
            move_history(config, original)
    operations = pending_operations(config)
    assert len(operations) == 1
    assert backup_batches(config) == []
    assert inventory(config) == []
    with pytest.raises(StorageError, match='recovery_required'):
        move_history(config, original)
    recover_operation(config, operations[0]['id'])
    assert inventory(config) == original
    assert pending_operations(config) == []
    recover_operation(config, operations[0]['id'])  # Idempotent confirmation.
    assert not state.exists()
    assert len(list(runs.glob('*/events.jsonl'))) == 2


def test_interruption_after_all_moves_before_commit_recovers(tmp_path, monkeypatch):
    import thsr_ticket.storage_journal as journal
    config, _, _ = records(tmp_path)
    original = inventory(config)
    write = journal.atomic_json

    def crash_before_commit(path, data):
        if data['status'] == 'complete':
            raise ProcessInterrupted()
        return write(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(journal, 'atomic_json', crash_before_commit)
        with pytest.raises(ProcessInterrupted):
            move_history(config, original)
    recover_operation(config, pending_operations(config)[0]['id'])
    assert inventory(config) == original


def test_interrupted_restore_returns_to_backup(tmp_path, monkeypatch):
    config, _, runs = records(tmp_path)
    original = inventory(config)
    backup = move_history(config, original)
    with monkeypatch.context() as patch:
        interrupt_rename(patch, 2)
        with pytest.raises(ProcessInterrupted):
            restore_history(config, backup)
    recover_operation(config, pending_operations(config)[0]['id'])
    assert len(list(backup.glob('*/events.jsonl'))) == 2
    assert list(runs.glob('*/events.jsonl')) == []
    restore_history(config, backup)
    assert inventory(config) == original


def test_failed_journal_write_moves_nothing(tmp_path, monkeypatch):
    config, _, _ = records(tmp_path)
    original = inventory(config)

    def fail(*args):
        raise OSError(errno.ENOSPC, 'secret path')

    monkeypatch.setattr('thsr_ticket.storage_journal.atomic_json', fail)
    with pytest.raises(OSError):
        move_history(config, original)
    assert inventory(config) == original


def test_normal_failure_rolls_back_and_keeps_error_category(tmp_path, monkeypatch):
    config, _, _ = records(tmp_path)
    original = inventory(config)
    rename = Path.rename
    calls = []

    def fail_once(source, destination):
        calls.append(source)
        if len(calls) == 2:
            raise PermissionError('private')
        return rename(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', fail_once)
        with pytest.raises(PermissionError) as error:
            move_history(config, original)
        assert error_info(error.value)['code'] == 'permission_denied'
    assert inventory(config) == original
    assert not pending_operations(config)


def test_failed_automatic_rollback_leaves_recoverable_journal(tmp_path, monkeypatch):
    config, _, _ = records(tmp_path)
    original = inventory(config)
    rename = Path.rename
    calls = []

    def fail(source, destination):
        calls.append(source)
        if len(calls) >= 2:
            raise PermissionError('private')
        return rename(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', fail)
        with pytest.raises(StorageError, match='rollback_failed'):
            move_history(config, original)
    recover_operation(config, pending_operations(config)[0]['id'])
    assert inventory(config) == original


@pytest.mark.parametrize('conflict', ['duplicate', 'changed'])
def test_recovery_preflight_never_overwrites_conflicts(tmp_path, monkeypatch, conflict):
    config, _, runs = records(tmp_path)
    with monkeypatch.context() as patch:
        interrupt_rename(patch, 2)
        with pytest.raises(ProcessInterrupted):
            move_history(config, inventory(config))
    operation = pending_operations(config)[0]
    root = runs.parent / (runs.name + '.history-backups')
    backup = next(root.glob('*'))
    moved = next(backup.glob('*'))
    if conflict == 'duplicate':
        duplicate = runs / moved.name
        duplicate.mkdir()
        (duplicate / 'events.jsonl').write_bytes(b'original-location')
    else:
        (moved / 'events.jsonl').write_bytes(b'changed')
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('events.jsonl')}
    with pytest.raises(StorageError, match='recovery_conflict'):
        recover_operation(config, operation['id'])
    assert {str(p): p.read_bytes() for p in tmp_path.rglob('events.jsonl')} == before
    assert pending_operations(config)


def test_recovery_itself_can_be_interrupted_and_retried(tmp_path, monkeypatch):
    import thsr_ticket.storage_journal as journal
    config, _, _ = records(tmp_path)
    original = inventory(config)
    write = journal.atomic_json

    def crash(path, data):
        if data['status'] == 'complete':
            raise ProcessInterrupted()
        return write(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(journal, 'atomic_json', crash)
        with pytest.raises(ProcessInterrupted):
            move_history(config, original)
    identifier = pending_operations(config)[0]['id']
    with monkeypatch.context() as patch:
        interrupt_rename(patch, 2)
        with pytest.raises(ProcessInterrupted):
            recover_operation(config, identifier)
    recover_operation(config, identifier)
    assert inventory(config) == original


@pytest.mark.parametrize('content', ['broken', '{"version":2}', '{"version":true}'])
def test_invalid_journal_is_preserved_and_blocks_mutation(tmp_path, content):
    config, _, runs = records(tmp_path)
    original = inventory(config)
    root = runs.parent / (runs.name + '.operations')
    root.mkdir()
    path = root / ('f' * 32 + '.json')
    path.write_text(content, encoding='utf-8')
    assert not pending_operations(config)[0]['recoverable']
    with pytest.raises(StorageError, match='recovery_required'):
        move_history(config, original)
    with pytest.raises(StorageError, match='journal_invalid'):
        recover_operation(config, path.stem)
    assert path.read_text(encoding='utf-8') == content


def test_tampered_journal_cannot_escape_record_root(tmp_path, monkeypatch):
    config, _, runs = records(tmp_path)
    with monkeypatch.context() as patch:
        interrupt_rename(patch, 1)
        with pytest.raises(ProcessInterrupted):
            move_history(config, inventory(config))
    operation = pending_operations(config)[0]
    path = runs.parent / (runs.name + '.operations') / (operation['id'] + '.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    data['entries'][0]['id'] = '../outside'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(StorageError, match='journal_invalid'):
        recover_operation(config, operation['id'])


@pytest.mark.parametrize('error,code', [
    (PermissionError('SECRET'), 'permission_denied'),
    (RecordBusy('SECRET'), 'operation_busy'),
    (FileNotFoundError('SECRET'), 'records_changed'),
    (OSError(errno.ENOSPC, 'SECRET'), 'disk_full'),
    (OSError('SECRET'), 'io_error'),
    (RuntimeError('SECRET'), 'unexpected_error'),
    (StorageError('restore_conflict'), 'restore_conflict'),
])
def test_error_classification_does_not_expose_raw_text(error, code):
    info = error_info(error)
    assert info['code'] == code
    assert info['guidance']
    assert 'SECRET' not in json.dumps(info)

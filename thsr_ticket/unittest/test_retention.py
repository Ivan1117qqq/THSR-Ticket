import json
import os
from pathlib import Path
from datetime import datetime

import pytest
from thsr_ticket.automation import TAIPEI
from thsr_ticket.booking_records import record_paths
from thsr_ticket.retention import preview_cleanup, apply_cleanup
from thsr_ticket.storage_errors import StorageError


def query_run(config, number=1, root=None, result=False, finished=True):
    _, runs = record_paths(config)
    directory = (root or runs) / f'{number:032x}'
    directory.mkdir(parents=True)
    events = directory / 'events.jsonl'
    events.write_text(json.dumps({'event': 'run_started', 'query_only': True}) + '\n' +
                      json.dumps({'event': 'run_finished' if finished else 'stage'}) + '\n')
    os.utime(events, (946684800, 946684800))
    if result:
        (directory / 'result.json').write_text('{"tickets":[]}')
    return directory


def test_only_old_finished_query_logs_removed_and_audit_kept(tmp_path):
    config = tmp_path / 'booking.json'
    config.write_text('{}')
    old = query_run(config)
    booked = query_run(config, 2, result=True)
    pending = query_run(config, 3, finished=False)
    unknown = query_run(config, 4)
    (unknown / 'notes.txt').write_text('preserve')
    _, runs = record_paths(config)
    batch = runs.parent / (runs.name + '.history-backups') / ('b' * 32)
    backed_up = query_run(config, 5, batch)
    plan = preview_cleanup(config, 90, now=datetime(2026, 10, 23, tzinfo=TAIPEI))
    assert len(plan['items']) == 2 and plan['bytes'] > 0
    result = apply_cleanup(plan)
    assert result['status'] == 'completed' and result['deleted'] == 2
    assert not old.exists() and not backed_up.exists()
    assert booked.exists() and pending.exists() and unknown.exists()
    assert len(list((runs / 'cleanup').glob('*.json'))) == 1


def test_guard_and_changed_records_block_deletion(tmp_path):
    config = tmp_path / 'booking.json'
    config.write_text('{}')
    old = query_run(config)
    plan = preview_cleanup(config)
    state, _ = record_paths(config)
    state.write_text('{"status":"submission_pending"}')
    with pytest.raises(StorageError):
        apply_cleanup(plan)
    with pytest.raises(StorageError):
        preview_cleanup(config)
    state.unlink()
    (old / 'result.json').write_text('{}')
    with pytest.raises(StorageError):
        apply_cleanup(plan)
    assert (old / 'events.jsonl').exists()


def test_changed_log_and_unknown_new_file_are_preserved(tmp_path):
    config = tmp_path / 'booking.json'
    config.write_text('{}')
    directory = query_run(config)
    plan = preview_cleanup(config)
    (directory / 'events.jsonl').write_text('{"event":"run_finished","changed":true}\n')
    with pytest.raises(StorageError):
        apply_cleanup(plan)
    assert directory.exists()


def test_audit_failure_deletes_nothing(tmp_path, monkeypatch):
    config = tmp_path / 'booking.json'
    config.write_text('{}')
    directory = query_run(config)
    plan = preview_cleanup(config)
    monkeypatch.setattr('thsr_ticket.retention.atomic_json', lambda *a: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        apply_cleanup(plan)
    assert (directory / 'events.jsonl').exists()


def test_partial_cleanup_is_audited_and_unknown_files_remain(tmp_path, monkeypatch):
    config = tmp_path / 'booking.json'
    config.write_text('{}')
    first = query_run(config, 1)
    second = query_run(config, 2)
    plan = preview_cleanup(config)
    original = Path.unlink

    def fail_second(path, *args, **kwargs):
        if path == second / 'events.jsonl':
            raise PermissionError()
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', fail_second)
    with pytest.raises(StorageError, match='cleanup_partial'):
        apply_cleanup(plan)
    assert not first.exists() and (second / 'events.jsonl').exists()
    _, runs = record_paths(config)
    audit = json.loads(next((runs / 'cleanup').glob('*.json')).read_text(encoding='utf-8'))
    assert audit['status'] == 'partial' and audit['deleted'] == 1 and len(audit['entries']) == 2


def test_incomplete_restore_blocks_cleanup(tmp_path):
    from thsr_ticket.config_store import RESTORE_MARKER, ConfigRestoreError
    config = tmp_path / 'booking.json'
    config.write_text('{}')
    directory = query_run(config)
    plan = preview_cleanup(config)
    (tmp_path / RESTORE_MARKER).write_text('{}')
    with pytest.raises(ConfigRestoreError):
        apply_cleanup(plan)
    assert directory.exists()


@pytest.mark.parametrize('records', [
    [{'event': 'run_started', 'query_only': False}, {'event': 'run_finished'}],
    [{'event': 'run_started', 'query_only': True}, {'event': 'stage', 'phase': 'submit_ticket'},
     {'event': 'run_stopped', 'reason': 'booking_unconfirmed'}],
    [{'event': 'run_finished'}],
])
def test_missing_result_is_not_proof_of_query_only(tmp_path, records):
    config = tmp_path / 'booking.json'
    config.write_text('{}')
    directory = query_run(config)
    events = directory / 'events.jsonl'
    events.write_text(''.join(json.dumps(item) + '\n' for item in records))
    os.utime(events, (946684800, 946684800))
    assert not preview_cleanup(config)['items']
    assert events.exists()


@pytest.mark.parametrize('days', [0, -1, 3651, True])
def test_invalid_retention_period(tmp_path, days):
    with pytest.raises(ValueError):
        preview_cleanup(tmp_path / 'booking.json', days)

import json

import pytest

from thsr_ticket.booking_records import read_object, record_paths
from thsr_ticket.record_storage import inventory, move_history, restore_history, latest_backup


def fixture_run(tmp_path):
    config = tmp_path / 'booking.json'
    state, runs = record_paths(config)
    directory = runs / ('a' * 32)
    directory.mkdir(parents=True)
    (directory / 'events.jsonl').write_bytes(b'{"event":"run_finished"}\n')
    return config, state, directory


def test_move_restore_preserves_bytes(tmp_path):
    config, state, directory = fixture_run(tmp_path)
    expected = inventory(config)
    backup = move_history(config, expected)
    assert latest_backup(config) == backup
    assert not directory.exists()
    assert not state.exists()
    restore_history(config, backup)
    assert (directory / 'events.jsonl').read_bytes() == b'{"event":"run_finished"}\n'
    assert latest_backup(config) is None


def test_unfinished_and_future_records_are_preserved(tmp_path):
    config, _, directory = fixture_run(tmp_path)
    (directory / 'events.jsonl').write_text('{"event":"run_started"}', encoding='utf-8')
    assert inventory(config) == []
    (directory / 'events.jsonl').write_text('{"event":"run_finished","_record_version":2}', encoding='utf-8')
    assert inventory(config) == []


@pytest.mark.parametrize('content', ['broken', '{"status":"submission_pending"}', '{"status":"booked"}'])
def test_any_guard_blocks_cleanup(tmp_path, content):
    config, state, directory = fixture_run(tmp_path)
    expected = inventory(config)
    state.write_text(content, encoding='utf-8')
    assert inventory(config) == []
    with pytest.raises(ValueError):
        move_history(config, expected)
    assert directory.exists()
    assert state.read_text(encoding='utf-8') == content


def test_changed_files_require_new_preview(tmp_path):
    config, _, directory = fixture_run(tmp_path)
    expected = inventory(config)
    (directory / 'events.jsonl').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError):
        move_history(config, expected)
    assert directory.exists()


def test_unknown_files_are_preserved(tmp_path):
    config, _, directory = fixture_run(tmp_path)
    (directory / 'unknown.bin').write_bytes(b'private')
    assert inventory(config) == []


@pytest.mark.parametrize('version', [2, True, '1', None])
def test_unknown_record_version_is_read_only(tmp_path, version):
    path = tmp_path / 'state.json'
    original = json.dumps({'_record_version': version, 'status': 'booked'})
    path.write_text(original, encoding='utf-8')
    with pytest.raises(ValueError):
        read_object(path)
    assert path.read_text(encoding='utf-8') == original


def test_legacy_record_is_not_rewritten(tmp_path):
    path = tmp_path / 'state.json'
    path.write_bytes(b'{"status": "booked"}')
    assert read_object(path)['status'] == 'booked'
    assert path.read_bytes() == b'{"status": "booked"}'

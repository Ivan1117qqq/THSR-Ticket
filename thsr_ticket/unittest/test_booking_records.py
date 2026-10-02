import json
from unittest.mock import Mock

import pytest

from thsr_ticket.booking_records import archive_booking, record_paths, show_bookings
from thsr_ticket.run_records import RunRecords
from thsr_ticket.unittest.test_current_flow import html
from thsr_ticket.view_model.booking_result import BookingResult
from thsr_ticket.booking_records import pending_fingerprint, resolve_pending, record_entries
from thsr_ticket.record_lock import record_lock


@pytest.fixture
def files(tmp_path):
    config = tmp_path / 'booking.local.json'
    config.write_text('not a valid config; management must not read this')
    state, runs = record_paths(config)
    state.write_text(json.dumps({'status': 'booked', 'booking_codes': ['TEST1234']}))
    return config, state, runs


@pytest.mark.parametrize('outcome', ['booked', 'not_booked', 'cancelled'])
def test_verified_pending_preserves_original(files, outcome):
    config, state, _ = files
    state.write_text('{"status": "submission_pending", "train_id": 117}')
    original = state.read_bytes()
    fingerprint = pending_fingerprint(config)
    with pytest.raises(ValueError):
        resolve_pending(config, outcome, fingerprint, code='TEST1234')
    assert state.read_bytes() == original
    directory = resolve_pending(config, outcome, fingerprint, confirmed=True, code='TEST1234')
    assert not state.exists()
    assert (directory / 'state.json').read_bytes() == original
    assert json.loads((directory / 'resolution.json').read_text())['outcome'] == outcome
    assert record_entries(config)[0]['status'] == 'resolved'


def test_pending_stale_or_missing_code_keeps_blocker(files):
    config, state, _ = files
    state.write_text('{"status":"submission_pending"}')
    fingerprint = pending_fingerprint(config)
    with pytest.raises(ValueError):
        resolve_pending(config, 'booked', fingerprint, confirmed=True)
    state.write_text('{"status":"submission_pending","train_id":117}')
    original = state.read_bytes()
    with pytest.raises(ValueError):
        resolve_pending(config, 'not_booked', fingerprint, confirmed=True)
    assert state.read_bytes() == original


def test_active_operation_prevents_archive_and_releases_lock(files):
    config, state, _ = files
    with record_lock(state):
        with pytest.raises(RuntimeError):
            archive_booking(config, 'TEST1234')
        assert state.exists()
    archive_booking(config, 'TEST1234')
    assert not state.exists()


def test_pending_move_failure_preserves_blocker(files, monkeypatch):
    config, state, _ = files
    state.write_text('{"status":"submission_pending"}')
    original = state.read_bytes()
    monkeypatch.setattr(type(state), 'rename', Mock(side_effect=OSError('test failure')))
    with pytest.raises(OSError):
        resolve_pending(config, 'not_booked', pending_fingerprint(config), confirmed=True)
    assert state.read_bytes() == original
    assert len(record_entries(config)) == 1


def test_show_complete_and_legacy_records(files, capsys):
    config, state, _ = files
    original = state.read_bytes()
    show_bookings(config)
    assert 'TEST1234' in capsys.readouterr().out
    records = RunRecords(state)
    records.save_result(BookingResult().parse(html('result')), '2099-01-01')
    show_bookings(config)
    output = capsys.readouterr().out
    assert '完整結果' in output and '繳費期限' in output and '座位' in output
    assert state.read_bytes() == original


def test_archive_preserves_state_bytes_and_results(files, capsys):
    config, state, runs = files
    original = state.read_bytes()
    records = RunRecords(state)
    records.save_result(BookingResult().parse(html('result')), '2099-01-01')
    result = records.result_path.read_bytes()
    destination = archive_booking(config, 'TEST1234')
    assert destination.is_relative_to(runs)
    assert destination.read_bytes() == original
    assert not state.exists()
    assert records.result_path.read_bytes() == result
    show_bookings(config)
    assert '已封存：TEST1234' in capsys.readouterr().out


@pytest.mark.parametrize('data,code', [
    ({'status': 'booked', 'booking_codes': ['TEST1234']}, 'WRONG'),
    ({'status': 'submission_pending'}, 'TEST1234'),
    ({'status': 'unknown'}, 'TEST1234'),
    ({'status': 'booked', 'booking_codes': []}, 'TEST1234'),
])
def test_archive_rejects_unconfirmed_or_mismatched_record(files, data, code):
    config, state, runs = files
    state.write_text(json.dumps(data))
    original = state.read_bytes()
    with pytest.raises(ValueError):
        archive_booking(config, code)
    assert state.read_bytes() == original
    assert not runs.exists()
    assert not state.with_suffix('.archive.lock').exists()


def test_rename_failure_keeps_current_record(files, monkeypatch):
    config, state, _ = files
    original = state.read_bytes()
    monkeypatch.setattr(type(state), 'rename', Mock(side_effect=PermissionError()))
    with pytest.raises(PermissionError):
        archive_booking(config, 'TEST1234')
    assert state.read_bytes() == original
    assert not state.with_suffix('.archive.lock').exists()


def test_existing_archive_lock_is_not_removed(files):
    config, state, _ = files
    lock = state.with_suffix('.archive.lock')
    lock.write_text('another archive process')
    with pytest.raises(FileExistsError):
        archive_booking(config, 'TEST1234')
    assert lock.exists() and state.exists()


def test_corrupt_results_are_skipped(files, capsys):
    config, state, runs = files
    state.write_text('broken')
    bad = runs / 'bad' / 'result.json'
    bad.parent.mkdir(parents=True)
    bad.write_text('broken')
    good = RunRecords(state)
    good.save_result(BookingResult().parse(html('result')), '2099-01-01')
    show_bookings(config)
    output = capsys.readouterr().out
    assert '無法讀取' in output and 'TEST1234' in output
    assert state.read_text() == 'broken'


@pytest.mark.parametrize('option', [['--show-bookings'], ['--archive-booking', 'TEST1234']])
def test_cli_management_never_loads_personal_config_or_browser(files, monkeypatch, option):
    from thsr_ticket.main import main
    config, _, _ = files
    forbidden = Mock(side_effect=AssertionError('must remain offline'))
    monkeypatch.setattr('thsr_ticket.automation.AutomationConfig.load', forbidden)
    monkeypatch.setattr('thsr_ticket.remote.browser_request.BrowserRequest', forbidden)
    monkeypatch.setattr('sys.argv', ['thsr-ticket', '--config', str(config), *option])
    assert main() == 0
    forbidden.assert_not_called()


def test_no_state_archive_fails_without_creating_results(files):
    config, state, runs = files
    state.unlink()
    with pytest.raises(ValueError, match='沒有可封存'):
        archive_booking(config, 'TEST1234')
    assert not runs.exists()

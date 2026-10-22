import json
import io
import os
import queue
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

from thsr_ticket import history_diagnostics as history
from thsr_ticket.application import run_background, form_config
from thsr_ticket.booking_records import record_paths
from thsr_ticket.scan_report import ScanCancelled
from thsr_ticket.unittest.test_gui import values
from thsr_ticket.version import VERSION


def write_events(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(event) + '\n' for event in events), encoding='utf-8')
    return path


def test_history_redacts_private_values_and_keeps_recorded_environment(tmp_path):
    secret = 'PRIVATE-IDENTITY-PHONE-BOOKING-PATH'
    path = write_events(tmp_path / 'events.jsonl', [
        {'event': 'run_started', 'query_only': True, 'app_version': '0.3.3',
         'python_version': '3.11.9', 'platform': 'Windows', 'path': secret},
        {'event': 'stage', 'phase': 'query', 'personal_id': secret, 'code': secret},
        {'event': 'run_stopped', 'reason': 'network_timeout', 'message': secret},
    ])
    result = history.read_diagnostic(path)
    assert result['code'] == 'network'
    assert result['recorded_version'] == '0.3.3'
    assert secret not in json.dumps(result)
    assert result['snapshot']['recorded_environment'] == {
        'app_version': '0.3.3', 'python_version': '3.11.9', 'platform': 'Windows', 'query_only': True}
    assert result['snapshot']['viewer_app_version'] == VERSION


def test_legacy_version_is_unknown_and_event_window_is_bounded(tmp_path):
    path = write_events(tmp_path / 'events.jsonl', [
        {'event': 'run_started', 'app_version': 'PRIVATE', 'platform': 'PRIVATE'},
        *[{'event': 'stage', 'phase': 'query', 'attempt': n} for n in range(300)],
        {'event': 'run_finished', 'outcome': 'success'},
    ])
    result = history.read_diagnostic(path)
    assert result['recorded_version'] == 'unknown'
    assert result['snapshot']['recorded_environment']['platform'] == 'unknown'
    assert len(result['snapshot']['events']) == 200
    assert result['snapshot']['events'][0]['attempt'] == 101
    assert not result['partial']


@pytest.mark.parametrize('terminal,phase,query_only,code', [
    ({'event': 'run_finished', 'outcome': 'success'}, 'query', True, 'query_success'),
    ({'event': 'run_finished', 'outcome': 'attempt_limit'}, 'query', False, 'attempt_limit'),
    ({'event': 'run_finished', 'outcome': 'PRIVATE'}, 'query', False, 'failed'),
    ({'event': 'task_completed', 'outcome': 'browser_start'}, 'browser_start', False, 'browser_start'),
    ({'event': 'task_completed', 'outcome': 'ocr_load'}, 'ocr_load', False, 'ocr_unavailable'),
    ({'event': 'task_completed', 'outcome': 'network'}, 'submit_ticket', False, 'booking_unconfirmed'),
    ({'event': 'run_stopped', 'reason': 'interrupted'}, 'query', True, 'stopped'),
])
def test_terminal_categories(tmp_path, terminal, phase, query_only, code):
    path = write_events(tmp_path / 'events.jsonl', [
        {'event': 'run_started', 'query_only': query_only}, {'event': 'stage', 'phase': phase}, terminal])
    assert history.read_diagnostic(path)['code'] == code


def test_missing_terminal_and_save_failure_preserve_uncertainty(tmp_path):
    path = write_events(tmp_path / 'events.jsonl', [{'event': 'stage', 'phase': 'submit_ticket'}])
    assert history.read_diagnostic(path)['code'] == 'booking_unconfirmed'
    write_events(path, [{'event': 'state_update_failed'}, {'event': 'run_finished', 'outcome': 'success'}])
    assert history.read_diagnostic(path)['code'] == 'booking_unconfirmed'


def test_tail_read_is_bounded_and_retains_head_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'MAX_BYTES', 600)
    monkeypatch.setattr(history, 'MAX_LINE', 256)
    path = write_events(tmp_path / 'events.jsonl', [
        {'event': 'run_started', 'app_version': '0.3.3', 'query_only': True},
        {'private': 'x' * 4000}, {'event': 'stage', 'phase': 'query'},
        {'event': 'task_completed', 'outcome': 'network', 'phase': 'query'}])
    content = path.read_bytes()

    class GrowingStream(io.BytesIO):
        total = 0

        def readline(self, size=-1):
            line = super().readline(size)
            self.total += len(line)
            return line

    stream = GrowingStream(content + b'x' * 10000)
    original = Path.open
    monkeypatch.setattr(Path, 'open', lambda target, *args, **kwargs:
                        stream if target == path else original(target, *args, **kwargs))
    result = history.read_diagnostic(path)
    assert stream.total <= len(content.splitlines(keepends=True)[0]) + history.MAX_BYTES
    assert result['code'] == 'network'
    assert result['recorded_version'] == '0.3.3'
    assert result['partial']
    assert result['snapshot']['warnings']['tail_only']
    assert len(result['snapshot']['events']) == 2


def test_bad_lines_deep_json_and_huge_integer_do_not_abort_read(tmp_path):
    path = tmp_path / 'events.jsonl'
    path.write_bytes(b'not-json\n' + b'[' * 2000 + b']' * 2000 + b'\n' +
                     b'{"event":"stage","phase":"query","elapsed_ms":' + b'9' * 400 + b'}\n' +
                     b'{"event":"task_completed","outcome":"network"}\n')
    result = history.read_diagnostic(path)
    assert result['code'] == 'network'
    assert result['snapshot']['warnings']['malformed_lines'] == 2
    assert 'elapsed_ms' not in result['snapshot']['events'][0]


def test_changed_file_is_marked_incomplete(tmp_path, monkeypatch):
    path = write_events(tmp_path / 'events.jsonl', [{'event': 'run_finished', 'outcome': 'success'}])
    original = Path.stat
    calls = []

    def changed(target, *args, **kwargs):
        stat = original(target, *args, **kwargs)
        if target == path:
            calls.append(1)
            if len(calls) == 2:
                return Mock(st_size=stat.st_size + 1, st_mtime_ns=stat.st_mtime_ns, st_mtime=stat.st_mtime)
        return stat

    monkeypatch.setattr(history, 'linked', lambda path: False)
    monkeypatch.setattr(Path, 'stat', changed)
    result = history.read_diagnostic(path)
    assert result['code'] == 'incomplete' and result['partial']


def test_scan_includes_backups_and_limits_latest_runs(tmp_path, monkeypatch):
    config = tmp_path / 'booking.local.json'
    _, runs = record_paths(config)
    monkeypatch.setattr(history, 'MAX_RUNS', 2)
    for number in range(3):
        path = write_events(runs / f'{number:032x}' / 'events.jsonl', [{'event': 'run_finished'}])
        os.utime(path, ns=(number + 1, number + 1))
    batch = runs.parent / (runs.name + '.history-backups') / ('b' * 32)
    backup = write_events(batch / ('a' * 32) / 'events.jsonl', [{'event': 'run_stopped'}])
    os.utime(backup, ns=(100, 100))
    rows, snapshots, report = history.scan_history(config)
    assert len(rows) == len(snapshots) == 2
    assert rows[0]['id'].startswith('backups/')
    assert report['not_loaded'] == 2
    assert report['accepted'] == 2


def test_scan_skips_linked_and_unreadable_file_without_losing_good_run(tmp_path, monkeypatch):
    config = tmp_path / 'booking.local.json'
    _, runs = record_paths(config)
    for name in ('a', 'b', 'c'):
        write_events(runs / (name * 32) / 'events.jsonl', [{'event': 'run_finished'}])
    original = history.read_diagnostic

    def read(path, cancel):
        if path.parent.name == 'b' * 32:
            raise PermissionError('PRIVATE')
        return original(path, cancel)

    monkeypatch.setattr(history, 'read_diagnostic', read)
    monkeypatch.setattr(history, 'linked', lambda path: path.name == 'c' * 32)
    rows, _, report = history.scan_history(config)
    assert len(rows) == 1
    assert report['failed'] == report['skipped'] == 1
    assert 'PRIVATE' not in json.dumps(report)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ScanCancelled):
        history.scan_history(config, cancel)


def test_background_start_failure_is_saved_without_private_exception(tmp_path):
    path = tmp_path / 'booking.local.json'
    run_background(form_config(values()), path, True, threading.Event(), queue.Queue(),
                   client_factory=Mock(side_effect=RuntimeError('PRIVATE')), reader_factory=Mock())
    rows, snapshots, _ = history.scan_history(path)
    assert len(rows) == 1 and rows[0]['code'] == 'browser_start'
    assert snapshots[rows[0]['id']]['recorded_environment']['app_version'] == VERSION
    assert 'PRIVATE' not in json.dumps(snapshots)


def test_runner_uses_one_shared_log_including_preparation(tmp_path):
    from thsr_ticket.unittest.test_current_flow import html, response
    from thsr_ticket.captcha import CaptchaGuess
    path = tmp_path / 'booking.local.json'
    client = Mock()
    client.request_booking_page.return_value = response(html('booking'))
    client.request_security_code_img.return_value = response(b'fake', 'image/png')
    client.submit_booking_form.return_value = response(html('trains'))
    reader = Mock()
    reader.unavailable = False
    reader.recognize.return_value = CaptchaGuess('ABCD', 0.9)
    run_background(form_config(values()), path, True, threading.Event(), queue.Queue(),
                   client_factory=Mock(return_value=client), reader_factory=Mock(return_value=reader))
    _, runs = record_paths(path)
    files = list(runs.glob('*/events.jsonl'))
    assert len(files) == 1
    events = [json.loads(line) for line in files[0].read_text().splitlines()]
    assert [event['event'] for event in events].count('run_started') == 1
    assert any(event.get('phase') == 'preflight' for event in events)
    assert any(event['event'] == 'run_finished' and event['outcome'] == 'success' for event in events)
    assert events[-1]['event'] == 'task_completed'
    client.submit_ticket.assert_not_called()

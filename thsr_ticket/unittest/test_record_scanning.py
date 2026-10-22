import json
from pathlib import Path

import pytest

from thsr_ticket.booking_records import record_entries, record_paths
from thsr_ticket.record_storage import inventory, move_history
from thsr_ticket.scan_report import ScanReport


def make_run(config, number, event=None, result=False):
    _, runs = record_paths(config)
    directory = runs / f'{number:032x}'
    directory.mkdir(parents=True)
    (directory / 'events.jsonl').write_text(json.dumps(event or {'event': 'run_finished'}), encoding='utf-8')
    if result:
        (directory / 'result.json').write_text(json.dumps({'tickets': [{'id': f'DEMO{number}'}]}), encoding='utf-8')
    return directory


def test_scan_preserves_good_results_and_counts_each_reason(tmp_path, monkeypatch):
    config = tmp_path / 'booking.json'
    good = make_run(config, 1)
    bad = make_run(config, 2)
    (bad / 'events.jsonl').write_bytes(b'broken')
    make_run(config, 3, {'event': 'run_started'})
    make_run(config, 4, {'event': 'run_finished', '_record_version': 5})
    denied = make_run(config, 5)
    read = Path.open

    def open_file(path, *args, **kwargs):
        if path.parent == denied:
            raise PermissionError('PRIVATE')
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', open_file)
    report = ScanReport()
    assert [item['id'] for item in inventory(config, report=report)] == [good.name]
    summary = report.snapshot()
    assert summary['accepted'] == 1 and summary['skipped'] == 3 and summary['failed'] == 1
    assert summary['checked'] == 5
    assert {item['code'] for item in summary['reasons']} == {'malformed', 'unfinished', 'version', 'permission'}
    assert 'PRIVATE' not in json.dumps(summary)


def test_selected_validation_never_reads_unselected_records(tmp_path, monkeypatch):
    config = tmp_path / 'booking.json'
    good = make_run(config, 1)
    other = make_run(config, 2)
    selected = [item for item in inventory(config) if item['id'] == good.name]
    open_file = Path.open

    def forbidden(path, *args, **kwargs):
        if path.parent == other:
            raise AssertionError('Unselected content must not be read')
        return open_file(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', forbidden)
    destination = move_history(config, selected)
    assert (destination / good.name).exists()
    assert other.exists()


def test_booking_reader_reports_bad_files_and_keeps_good_tickets(tmp_path, monkeypatch):
    config = tmp_path / 'booking.json'
    make_run(config, 1, result=True)
    bad = make_run(config, 2, result=True)
    (bad / 'result.json').write_bytes(b'broken')
    denied = make_run(config, 3, result=True)
    read = Path.read_text

    def read_text(path, *args, **kwargs):
        if path.parent == denied:
            raise PermissionError('PRIVATE')
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read_text)
    report = ScanReport()
    entries = record_entries(config, report=report)
    assert [item['code'] for item in entries] == ['DEMO1']
    assert report.snapshot()['accepted'] == 1
    assert report.snapshot()['skipped'] == 1
    assert report.snapshot()['failed'] == 1


def test_root_permission_error_is_not_an_empty_success(tmp_path, monkeypatch):
    config = tmp_path / 'booking.json'
    _, runs = record_paths(config)
    enumerate_paths = Path.iterdir

    def iterdir(path):
        if path == runs:
            raise PermissionError('PRIVATE')
        return enumerate_paths(path)

    monkeypatch.setattr(Path, 'iterdir', iterdir)
    with pytest.raises(PermissionError):
        inventory(config)
    with pytest.raises(PermissionError):
        record_entries(config)

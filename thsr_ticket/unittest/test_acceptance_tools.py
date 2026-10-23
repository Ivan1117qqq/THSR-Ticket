"""Acceptance must not hide skipped checks, damaged evidence or real user files."""
import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from scripts.review_desktop import create_review_data
from scripts.verify_acceptance import test_results as junit_results, verify_artifact, source_snapshot, repository_checks
from thsr_ticket.automation import AutomationConfig
from thsr_ticket.booking_records import record_entries
from thsr_ticket.record_storage import inventory
from thsr_ticket.task_status import booking_guard


def test_review_fixtures_have_known_results_and_cannot_be_used_for_booking(tmp_path):
    root = create_review_data(tmp_path / 'review')
    booked = root / 'booked/booking.local.json'
    entries = record_entries(booked)
    assert len(entries) == 31 and sum(item['current'] for item in entries) == 1
    assert {item['code'] for item in entries} == {f'DEMO{number:04d}' for number in range(1, 32)}
    assert booking_guard(booked) == 'booked'
    assert booking_guard(root / 'pending/booking.local.json') == 'pending'
    assert len(inventory(root / 'logs/booking.local.json')) == 3
    for case in ('booked', 'pending', 'logs', 'backup'):
        with pytest.raises(ValidationError):
            AutomationConfig.load(root / case / 'booking.local.json')


def test_review_generation_never_overwrites_existing_data(tmp_path):
    root = create_review_data(tmp_path / 'review')
    file = root / 'booked/booking.local.state.json'
    before = file.read_bytes()
    with pytest.raises(FileExistsError):
        create_review_data(root)
    assert file.read_bytes() == before


def test_only_explicit_live_test_skip_is_accepted(tmp_path):
    path = tmp_path / 'results.xml'
    path.write_text('<testsuites><testsuite><testcase classname="offline" name="works"/>'
                    '<testcase classname="thsr_ticket.unittest.test_http_request" name="test_requests_work">'
                    '<skipped/></testcase></testsuite></testsuites>')
    result = junit_results(path)
    assert result['accepted'] and result['passed'] == 1 and len(result['skipped']) == 1
    path.write_text('<testsuite><testcase classname="desktop" name="missing"><skipped/></testcase></testsuite>')
    assert not junit_results(path)['accepted']
    path.write_text('<testsuite><testcase classname="desktop" name="fails"><failure/></testcase></testsuite>')
    assert junit_results(path)['failed'] == 1 and not junit_results(path)['accepted']
    path.write_text('<testsuite/>')
    with pytest.raises(ValueError):
        junit_results(path)


def test_success_exit_without_complete_runtime_evidence_is_not_accepted(tmp_path):
    report = {'qml': True, 'ocr_standard': True, 'ocr_beta': False, 'playwright_driver': True, 'private_storage': True}
    (tmp_path / 'runtime.json').write_text(json.dumps(report))
    with pytest.raises(ValueError):
        verify_artifact(tmp_path, 'runtime')
    (tmp_path / 'runtime.json').unlink()
    with pytest.raises(OSError):
        verify_artifact(tmp_path, 'runtime')


def test_source_fingerprint_detects_content_changes_not_private_data(tmp_path):
    source = tmp_path / 'thsr_ticket/module.py'
    source.parent.mkdir()
    source.write_text('old')
    before = source_snapshot(tmp_path)
    (tmp_path / 'booking.local.json').write_text('not source; do not inspect')
    assert source_snapshot(tmp_path) == before
    source.write_text('new')
    after = source_snapshot(tmp_path)
    assert after['files'] == before['files'] and after['sha256'] != before['sha256']


def test_batch_keeps_manual_checks_pending_when_artifact_is_missing(tmp_path, monkeypatch):
    from scripts import verify_acceptance as batch
    output = tmp_path / 'new-report'
    monkeypatch.setattr('sys.argv', ['verify_acceptance', '--output', str(output)])
    monkeypatch.setattr('sys.platform', 'win32')
    monkeypatch.setattr(batch, 'steps', lambda *a: [('runtime', [])])
    result = {'name': 'runtime', 'status': 'passed', 'log': 'runtime.log'}
    monkeypatch.setattr(batch, 'run_step', Mock(return_value=result))
    monkeypatch.setattr(batch, 'repository_checks', lambda *a: {'passed': True})
    assert batch.main() == 1
    report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
    assert report['status'] == 'failed' and report['steps'][0]['artifact_invalid']
    assert all(item['status'] in ('not_run', 'needs_data') for item in report['manual'])
    assert 'failed' in (output / 'summary.md').read_text(encoding='utf-8')


def test_repository_check_rejects_broken_links_and_missing_code_index(tmp_path):
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'thsr_ticket').mkdir()
    (tmp_path / 'README.md').write_text('[missing](docs/missing.md)')
    (tmp_path / 'CHANGELOG.md').write_text('')
    (tmp_path / 'docs/file-inventory.md').write_text('')
    (tmp_path / 'thsr_ticket/example.py').write_text('')
    result = repository_checks(tmp_path)
    assert not result['passed'] and result['missing_links'] and result['unindexed_code']

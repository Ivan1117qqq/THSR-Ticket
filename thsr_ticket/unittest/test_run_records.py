import json
from unittest.mock import Mock

import pytest
from requests import Timeout

from thsr_ticket.run_records import RunRecords, atomic_json
from thsr_ticket.unittest import test_automation
from thsr_ticket.unittest.test_automation import captcha_error
from thsr_ticket.unittest.test_current_flow import html, response


config = test_automation.config
runner = test_automation.runner


def events(runner):
    return [json.loads(line) for line in runner.records.events_path.read_text(encoding='utf-8').splitlines()]


def test_complete_result_and_private_data_not_in_events(runner):
    runner.config.phone_num = '0912345678'
    assert runner.run()
    result = json.loads(runner.records.result_path.read_text(encoding='utf-8'))
    ticket = result['tickets'][0]
    assert result['status'] == 'booked'
    assert result['payment_status'] == 'unpaid'
    assert ticket['id'] == 'TEST1234'
    for field in ('date', 'start_station', 'dest_station', 'train_id', 'depart_time', 'arrival_time',
                  'seat', 'seat_class', 'price', 'payment_deadline', 'ticket_num_info'):
        assert ticket[field]
    log = runner.records.events_path.read_text(encoding='utf-8')
    for secret in (runner.config.personal_id, runner.config.phone_num, 'ABCD', 'TEST1234', 'session-token'):
        assert secret not in log
    serialized = runner.records.result_path.read_text(encoding='utf-8')
    assert runner.config.personal_id not in serialized
    assert runner.config.phone_num not in serialized
    stages = [row for row in events(runner) if row['event'] == 'stage']
    assert {row['phase'] for row in stages} == {
        'homepage', 'captcha_image', 'ocr', 'query', 'select_train', 'submit_ticket'}
    assert all(row['elapsed_ms'] >= 0 for row in stages)


def test_retry_records_and_query_only_have_no_result(runner):
    runner.client.submit_booking_form.side_effect = [captcha_error(), response(html('trains'))]
    assert runner.run(query_only=True)
    outcomes = [row['outcome'] for row in events(runner) if row['event'] == 'attempt_finished']
    assert outcomes == ['captcha_rejected', 'query_match']
    assert not runner.records.result_path.exists()
    first = runner.records.directory
    runner.client.submit_booking_form.side_effect = None
    runner.client.submit_booking_form.return_value = response(html('trains'))
    assert runner.run(query_only=True)
    assert runner.records.directory != first
    assert (first / 'events.jsonl').exists()


def test_network_failure_logs_category_not_exception_text(runner):
    runner.client.submit_booking_form.side_effect = Timeout('private A123456789 0912345678')
    with pytest.raises(Timeout):
        runner.run()
    log = events(runner)
    assert log[-1]['reason'] == 'network_timeout'
    assert log[-1]['phase'] == 'query'
    assert 'private' not in runner.records.events_path.read_text()
    assert not runner.records.result_path.exists()


def test_final_uncertainty_preserves_marker_and_logs_no_result(runner):
    runner.client.submit_ticket.side_effect = Timeout()
    with pytest.raises(RuntimeError):
        runner.run()
    assert events(runner)[-1]['reason'] == 'booking_unconfirmed'
    assert not runner.records.result_path.exists()
    assert json.loads(runner.state_path.read_text())['status'] == 'submission_pending'
    runner.client.submit_ticket.assert_called_once()


def test_log_write_failure_does_not_repeat_booking(runner, monkeypatch, capsys):
    original = type(runner.state_path).open

    def fail_log(path, *args, **kwargs):
        if path.name == 'events.jsonl':
            raise PermissionError('private')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(type(runner.state_path), 'open', fail_log)
    assert runner.run()
    assert runner.records.result_path.exists()
    runner.client.submit_ticket.assert_called_once()
    output = capsys.readouterr().out
    assert output.count('執行紀錄無法寫入') == 1
    assert 'private' not in output


def test_result_save_failure_still_shows_booking_code(runner, monkeypatch, capsys):
    monkeypatch.setattr(RunRecords, 'save_result', Mock(side_effect=OSError()))
    assert runner.run()
    output = capsys.readouterr().out
    assert 'TEST1234' in output
    assert '完整結果無法存檔' in output
    assert json.loads(runner.state_path.read_text())['status'] == 'booked'
    runner.client.submit_ticket.assert_called_once()


def test_state_update_failure_preserves_pending_and_complete_result(runner, monkeypatch):
    monkeypatch.setattr('thsr_ticket.automation.atomic_json', Mock(side_effect=OSError()))
    assert runner.run()
    assert runner.records.result_path.exists()
    assert json.loads(runner.state_path.read_text())['status'] == 'submission_pending'
    with pytest.raises(RuntimeError, match='已有訂位'):
        runner.run()
    runner.client.submit_ticket.assert_called_once()


def test_atomic_write_keeps_old_file_on_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / 'state.json'
    path.write_text('{"status":"submission_pending"}')
    monkeypatch.setattr('thsr_ticket.run_records.os.replace', Mock(side_effect=OSError()))
    with pytest.raises(OSError):
        atomic_json(path, {'status': 'booked'})
    assert json.loads(path.read_text())['status'] == 'submission_pending'
    assert list(tmp_path.iterdir()) == [path]


def test_interrupt_during_retry_does_not_duplicate_attempt(runner):
    runner.client.submit_booking_form.return_value = captcha_error()
    runner.sleep.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        runner.run()
    assert len([row for row in events(runner) if row['event'] == 'attempt_finished']) == 1
    assert events(runner)[-1]['reason'] == 'interrupted'

import json
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from requests import Timeout

from thsr_ticket.automation import AutomationConfig, AutomationRunner, TAIPEI, query_time, wait_until
from thsr_ticket.captcha import CaptchaGuess, CaptchaReader
from thsr_ticket.configs.web.param_schema import Train
from thsr_ticket.unittest.test_current_flow import html, response


@pytest.fixture
def config():
    return AutomationConfig(start_at='2099-01-01T00:00:00', start_station=2, dest_station=12,
                            outbound_date='2099-01-15', personal_id='A123456789', interval_seconds=0.5)


@pytest.fixture
def runner(config, tmp_path, monkeypatch):
    monkeypatch.setattr('builtins.input', Mock(side_effect=AssertionError('Unexpected input')))
    client = Mock()
    client.request_booking_page.return_value = response(html('booking'))
    client.request_security_code_img.return_value = response(b'image', 'image/png')
    client.submit_booking_form.return_value = response(html('trains'))
    client.submit_train.return_value = response(html('confirmation'))
    client.submit_ticket.return_value = response(html('result'))
    reader = Mock()
    reader.recognize.return_value = CaptchaGuess('ABCD', 0.9)
    return AutomationRunner(config, client, reader, tmp_path / 'booking.state.json', sleep=Mock())


@pytest.mark.parametrize('change', [
    {'interval_seconds': 0}, {'interval_seconds': -0.5}, {'interval_seconds': float('nan')},
    {'interval_seconds': float('inf')}, {'max_attempts': 0}, {'dest_station': 2},
    {'earliest_departure': '25:00'}, {'latest_departure': '09:00'}, {'adult_tickets': 0},
    {'adult_tickets': 10, 'child_tickets': 1}, {'personal_id': 'invalid'},
    {'train_ids': [615, 615]}, {'start_at': '2099-02-01'}, {'unknown': 'typo'},
])
def test_invalid_settings(config, change):
    with pytest.raises(ValidationError):
        AutomationConfig(**{**config.dict(), **change})


def test_schedule_clock_and_fractional_interval(config):
    assert config.start_at.utcoffset() == timedelta(hours=8)
    assert config.interval_seconds == 0.5
    target = datetime(2099, 1, 1, tzinfo=TAIPEI)
    now = Mock(side_effect=[target - timedelta(seconds=30.5), target - timedelta(seconds=0.5), target])
    sleep = Mock()
    wait_until(target, now, sleep)
    assert [call.args[0] for call in sleep.call_args_list] == [30, 0.5]
    wait_until(target, lambda: target + timedelta(seconds=1), sleep)
    assert sleep.call_count == 2


def test_selection_priority_and_time_window(config):
    def train(number, depart):
        return Train(id=number, depart=depart, arrive='12:00', travel_time='1:00',
                     discount_str='', form_value=str(number))
    trains = [train(615, '09:30'), train(617, '10:00'), train(619, '09:00')]
    assert config.select(trains).id == 615
    config.train_ids = [619, 617, 615]
    assert config.select(trains).id == 617
    config.latest_departure = '09:45'
    assert config.select(trains).id == 615
    config.train_ids = [999]
    assert config.select(trains) is None
    assert query_time('09:45') == '930A'
    assert query_time('12:15') == '1200N'
    assert query_time('00:15') == '1201A'
    assert query_time('05:30') == '1230A'


def test_automatic_booking_and_restart_guard(runner):
    assert runner.run()
    runner.client.submit_ticket.assert_called_once()
    params = runner.client.submit_ticket.call_args.args[0]
    assert params['dummyId'] == runner.config.personal_id
    state = json.loads(runner.state_path.read_text())
    assert state == {'status': 'booked', 'booking_codes': ['TEST1234']}
    with pytest.raises(RuntimeError, match='已有訂位'):
        runner.run()
    assert runner.client.request_booking_page.call_count == 1


def test_no_matches_requery_then_success(runner):
    runner.client.submit_booking_form.side_effect = [
        response(b'<form id="BookingS2Form"></form>'), response(html('trains'))]
    assert runner.run()
    runner.sleep.assert_called_once_with(0.5)
    assert runner.client.request_booking_page.call_count == 2
    runner.client.submit_ticket.assert_called_once()


def test_explicit_no_seats_feedback_retries_but_mixed_errors_stop(runner):
    sold_out = '<span class="feedbackPanelERROR">查無符合條件之車次</span>'.encode('utf-8')
    runner.client.submit_booking_form.side_effect = [response(sold_out), response(html('trains'))]
    assert runner.run(query_only=True)
    runner.sleep.assert_called_once_with(0.5)
    runner.client.submit_booking_form.side_effect = None
    runner.client.submit_booking_form.return_value = response(
        sold_out + b'<span class="feedbackPanelERROR">invalid captcha</span>')
    with pytest.raises(RuntimeError, match='網站拒絕'):
        runner.run()
    runner.client.submit_ticket.assert_not_called()


def test_attempt_limit_and_query_only(runner):
    runner.config.max_attempts = 2
    runner.config.train_ids = [999]
    assert not runner.run()
    runner.sleep.assert_called_once_with(0.5)
    runner.client.submit_train.assert_not_called()
    runner.config.train_ids = []
    assert runner.run(query_only=True)
    runner.client.submit_train.assert_not_called()
    assert not runner.state_path.exists()


@pytest.mark.parametrize('failure', ['ocr', 'rejected', 'unexpected', 'timeout', 'select'])
def test_failures_stop_without_booking(runner, failure):
    if failure == 'ocr':
        runner.reader.recognize.return_value = None
    elif failure == 'rejected':
        runner.client.submit_booking_form.return_value = response(
            b'<span class="feedbackPanelERROR">invalid captcha</span>')
    elif failure == 'unexpected':
        runner.client.submit_booking_form.return_value = response(b'<html></html>')
    elif failure == 'timeout':
        runner.client.submit_booking_form.side_effect = Timeout()
    else:
        runner.client.submit_train.side_effect = Timeout()
    with pytest.raises((RuntimeError, Timeout)):
        runner.run()
    runner.client.submit_ticket.assert_not_called()
    runner.sleep.assert_not_called()


@pytest.mark.parametrize('failure', ['timeout', 'unparseable', 'rejected', 'interrupt'])
def test_uncertain_final_submission_never_repeated(runner, failure):
    if failure == 'timeout':
        runner.client.submit_ticket.side_effect = Timeout()
    elif failure == 'interrupt':
        runner.client.submit_ticket.side_effect = KeyboardInterrupt()
    elif failure == 'rejected':
        runner.client.submit_ticket.return_value = response(b'<span class="feedbackPanelERROR">error</span>')
    else:
        runner.client.submit_ticket.return_value = response(b'<html></html>')
    with pytest.raises((RuntimeError, KeyboardInterrupt)):
        runner.run()
    assert json.loads(runner.state_path.read_text())['status'] == 'submission_pending'
    with pytest.raises(RuntimeError, match='已有訂位'):
        runner.run()
    runner.client.submit_ticket.assert_called_once()


def test_racing_submission_is_blocked(runner):
    def other_process(*args):
        runner.state_path.write_text('{}')
        return response(html('confirmation'))
    runner.client.submit_train.side_effect = other_process
    with pytest.raises(FileExistsError):
        runner.run()
    runner.client.submit_ticket.assert_not_called()


def test_cli_validate_never_opens_browser(config, tmp_path, monkeypatch, capsys):
    from thsr_ticket.main import main
    path = tmp_path / 'config.json'
    path.write_text(config.json(), encoding='utf-8')
    browser = Mock(side_effect=AssertionError('Unexpected browser'))
    monkeypatch.setattr('thsr_ticket.remote.browser_request.BrowserRequest', browser)
    monkeypatch.setattr('sys.argv', ['thsr-ticket', '--config', str(path), '--validate-config'])
    assert main() == 0
    assert config.personal_id not in capsys.readouterr().out
    browser.assert_not_called()


def test_ocr_preload_once_and_missing_engine_stops():
    factory = Mock(return_value=Mock())
    reader = CaptchaReader(engine_factory=factory)
    assert reader.prepare()
    assert reader.prepare()
    factory.assert_called_once()
    factory.side_effect = ImportError()
    failed = CaptchaReader(engine_factory=factory)
    assert not failed.prepare()
    assert failed.recognize(b'image') is None
    assert factory.call_count == 2

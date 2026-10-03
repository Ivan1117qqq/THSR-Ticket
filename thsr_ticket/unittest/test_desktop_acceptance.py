"""Offline acceptance through the same worker and core used by Qt; no website access."""
import json
import queue
import threading
import sys
from unittest.mock import Mock

import pytest
from requests import Timeout

from thsr_ticket.application import form_config, run_background
from thsr_ticket.captcha import CaptchaGuess
from thsr_ticket.unittest.test_current_flow import html, response
from thsr_ticket.unittest.test_gui import values


@pytest.mark.parametrize('scenario', ['query', 'book', 'disconnect'])
def test_worker_full_booking_flow(tmp_path, scenario):
    client = Mock()
    client.request_booking_page.return_value = response(html('booking'))
    client.request_security_code_img.return_value = response(b'image', 'image/png')
    client.submit_booking_form.return_value = response(html('trains'))
    client.submit_train.return_value = response(html('confirmation'))
    client.submit_ticket.return_value = response(html('result'))
    if scenario == 'disconnect':
        client.submit_ticket.side_effect = Timeout('private response must not appear')
    reader = Mock(unavailable=False)
    reader.recognize.return_value = CaptchaGuess('ABCD', 0.9)
    messages = queue.Queue()
    path = tmp_path / 'booking.local.json'
    config = form_config(values())
    stdout = sys.stdout
    run_background(config, path, scenario == 'query', threading.Event(), messages,
                   Mock(return_value=client), Mock(return_value=reader))
    assert sys.stdout is stdout
    state = path.with_suffix('.state.json')
    if scenario == 'query':
        assert not state.exists()
        client.submit_ticket.assert_not_called()
    else:
        client.submit_ticket.assert_called_once()
        assert json.loads(state.read_text())['status'] == ('booked' if scenario == 'book' else 'submission_pending')
    client.close.assert_called_once()
    events = list(messages.queue)
    assert events[-1][0] == 'done'
    assert 'private response' not in str(events)
    completion = next(value for kind, value in events if kind == 'completion')
    assert completion['code'] == ('booking_unconfirmed' if scenario == 'disconnect' else 'success')

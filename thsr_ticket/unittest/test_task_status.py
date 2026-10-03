import json

import pytest

from thsr_ticket.task_status import booking_guard, load_task, save_task, task_view
from thsr_ticket.application import protected_config_path


def test_task_summary_cannot_be_overwritten_as_booking_config():
    assert protected_config_path('booking.local.task.json')


@pytest.mark.parametrize('payload,expected', [
    ({'status': 'submission_pending'}, 'pending'),
    ({'status': 'booked', 'booking_codes': ['DEMO']}, 'booked'),
    ({'status': 'booked', 'booking_codes': []}, 'unreadable'),
    ({'status': 'unexpected'}, 'unreadable'),
    ([], 'unreadable'),
])
def test_booking_state_overrides_task_summary(tmp_path, payload, expected):
    path = tmp_path / 'booking.json'
    path.with_suffix('.state.json').write_text(json.dumps(payload))
    view = task_view({'code': 'success', 'query_only': True}, booking_guard(path))
    assert view['code'] == expected
    assert not view['can_book']
    assert view['action'] == 'records'


def test_corrupt_state_is_blocked_and_left_untouched(tmp_path):
    path = tmp_path / 'booking.json'
    state = path.with_suffix('.state.json')
    state.write_bytes(b'{broken')
    assert booking_guard(path) == 'unreadable'
    assert state.read_bytes() == b'{broken'


def test_task_summary_roundtrip_and_unknown_data(tmp_path):
    path = tmp_path / 'booking.json'
    assert load_task(path) == {}
    assert booking_guard(path) == ''
    save_task(path, 'running', True)
    data = json.loads(path.with_suffix('.task.json').read_text())
    assert set(data) == {'version', 'code', 'query_only', 'updated_at'}
    assert task_view(load_task(path))['code'] == 'interrupted'
    assert task_view(load_task(path), running=True)['code'] == 'running'
    with pytest.raises(ValueError):
        save_task(path, 'arbitrary private text', True)
    path.with_suffix('.task.json').write_text('{"version":1,"code":[],"query_only":false}')
    assert load_task(path) == {'code': 'summary_unreadable'}


@pytest.mark.parametrize('code,action', [
    ('network', 'edit'), ('attempt_limit', 'edit'), ('website_rejected', 'official'),
    ('ocr_load', 'settings'), ('browser_start', 'settings'),
])
def test_recovery_routes_are_specific(code, action):
    assert task_view({'code': code})['action'] == action

"""Local preset privacy, date ambiguity and reminder eligibility contracts."""
import json
from datetime import datetime

import pytest

from thsr_ticket.automation import TAIPEI
from thsr_ticket.journey_planning import PlanningIndex, deadline_time, journey_date
from thsr_ticket.journey_templates import FIELDS, TemplateStore


def preset():
    return dict(start_station='台北', dest_station='台中', class_type='標準', earliest_departure='09:00',
                latest_departure='20:00', train_ids='0117, 123', adult_tickets='1', child_tickets='0',
                disabled_tickets='0', elder_tickets='0', college_tickets='0', interval_seconds='1',
                max_attempts='60', ocr_model='standard', network_failure_limit='3', max_network_delay_seconds='30',
                personal_id='NEVER-STORE', phone_num='PRIVATE', start_at='2099-01-01', outbound_date='2099-01-02')


def entry(**changes):
    value = {'status': 'booked', 'current': True, 'code': 'TEST0001', 'ticket': {
        'date': '2099-01-15', 'depart_time': '09:31', 'start_station': '台北', 'dest_station': '台中',
        'train_id': '0117', 'payment_deadline': '2099-01-14 12:00'}}
    value.update(changes)
    return value


def test_template_lifecycle_never_serializes_credentials_dates_or_booking_state(tmp_path):
    store = TemplateStore(tmp_path)
    identifier = store.save('週末返家', {**preset(), 'booking_codes': ['SECRET']})
    assert set(store.read()[0]['values']) == set(FIELDS)
    text = store.path.read_text(encoding='utf-8')
    assert all(secret not in text for secret in ('NEVER-STORE', 'PRIVATE', 'SECRET', '2099-01'))
    store.save('返家', preset(), identifier)
    assert len(store.read()) == 1 and store.read()[0]['name'] == '返家'
    with pytest.raises(ValueError):
        store.save('返家', preset())
    store.delete(identifier)
    assert store.read() == []


@pytest.mark.parametrize('changes', [dict(start_station='不存在'), dict(dest_station='台北'),
                                     dict(earliest_departure='25:00'), dict(latest_departure='08:00'),
                                     dict(adult_tickets='0'), dict(child_tickets='11'),
                                     dict(train_ids='117,0117'), dict(interval_seconds='nan'),
                                     dict(max_network_delay_seconds='inf'), dict(network_failure_limit='101')])
def test_invalid_preset_does_not_overwrite_existing(tmp_path, changes):
    store = TemplateStore(tmp_path)
    identifier = store.save('keep', preset())
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.save('changed', {**preset(), **changes}, identifier)
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('damage', ['version', 'secret', 'broken'])
def test_invalid_template_store_is_retained(tmp_path, damage):
    store = TemplateStore(tmp_path)
    store.save('keep', preset())
    value = json.loads(store.path.read_text(encoding='utf-8'))
    if damage == 'version':
        value['version'] = 99
    else:
        value['items'][0]['values']['personal_id'] = 'SHOULD-NOT-EXIST'
    store.path.write_text('broken' if damage == 'broken' else json.dumps(value), encoding='utf-8')
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.save('new', preset())
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('raw,requested,expected', [
    ('01/15', '2099-01-15', '2099-01-15'), ('01/16', '2099-01-15', ''),
    ('01/15', '', ''), ('2099/01/15', '', '2099-01-15'), ('2099-01-16', '2099-01-15', ''),
    ('2000-02-29', '', '2000-02-29'), ('2100-02-29', '', '')])
def test_calendar_date_never_guesses_year(raw, requested, expected):
    actual = journey_date({'date': raw, 'requested_outbound_date': requested})
    assert (actual.isoformat() if actual else '') == expected


@pytest.mark.parametrize('raw', ['01/14', '01/14 12:00', '2099-01-14', '2099-02-30 12:00',
                                 '2099-01-14 24:00', '2099-01-14 12:00 garbage'])
def test_ambiguous_or_invalid_deadline_is_not_scheduled(raw):
    assert deadline_time(raw) is None


def test_explicit_timezone_is_converted_to_taiwan():
    assert deadline_time('2099-01-14T04:00:00Z').isoformat() == '2099-01-14T12:00:00+08:00'


def test_agenda_separates_paid_cancelled_history_pending_and_expired():
    now = datetime(2099, 1, 14, 10, tzinfo=TAIPEI)
    records = [entry(), entry(code='PAID', official_status='paid'), entry(code='CANCEL', resolution='cancelled'),
               entry(code='HISTORY', status='history', current=False),
               entry(code='', status='submission_pending'),
               entry(code='EXPIRED', ticket={**entry()['ticket'], 'payment_deadline': '2099-01-14 09:00'})]
    index = PlanningIndex(records)
    agenda = index.agenda(now, {})
    assert (agenda['payment'], agenda['pending'], agenda['upcoming']) == (2, 1, 4)
    assert len(agenda['reminders']) == 1
    assert agenda['items'][0]['pending']
    assert any(row['expired'] for row in agenda['items'])
    assert index.calendar(2099, 1, '2099-01-15')['total'] == 5


def test_calendar_and_todos_are_bounded_without_losing_counts():
    index = PlanningIndex([entry(code=f'TEST{number}') for number in range(100)])
    agenda = index.agenda(datetime(2099, 1, 14, tzinfo=TAIPEI), {})
    month = index.calendar(2099, 1, '2099-01-15')
    assert agenda['total'] == 100 and len(agenda['items']) == 6
    assert month['total'] == 100 and len(month['items']) == 8 and len(month['cells']) == 42
    assert sum(cell['count'] for cell in month['cells']) == 100


def test_deadline_after_departure_and_departed_journeys_do_not_notify():
    row = entry(ticket={**entry()['ticket'], 'payment_deadline': '2099-01-15 09:32'})
    index = PlanningIndex([row])
    assert not index.agenda(datetime(2099, 1, 14, tzinfo=TAIPEI), {})['reminders']
    assert index.agenda(datetime(2099, 1, 15, 10, tzinfo=TAIPEI), {})['payment'] == 0

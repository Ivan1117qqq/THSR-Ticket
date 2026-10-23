"""Synthetic contracts; these pages are not captured authenticated THSR responses."""
import json

import pytest
from thsr_ticket.booking_records import pending_fingerprint, record_paths
from thsr_ticket.official_booking import parse_official, OfficialEvidence
from thsr_ticket.run_records import atomic_json
from thsr_ticket.storage_errors import StorageError

CODE = '12345678'
TRIP = {'date': '2099-01-15', 'train_id': '0117', 'start_station': '台北', 'dest_station': '台中',
        'depart_time': '09:31'}


def page(status='未付款', code=CODE, trip='2099/01/15 台北 台中 09:31 10:18 117'):
    return ('<table><tr><th>訂位代號</th><td>' + code + '</td></tr>'
            '<tr><th>付款狀態</th><td>' + status + '</td></tr></table>'
            '<table><tr>' + ''.join('<td>' + value + '</td>' for value in trip.split()) + '</tr></table>')


@pytest.mark.parametrize('value,status', [
    ('未付款', 'unpaid'), ('已付款', 'paid'), ('已取票', 'collected'), ('已取消', 'cancelled')])
def test_structured_status_and_exact_trip(value, status):
    result = parse_official(page(value), CODE, TRIP)
    assert result['status'] == status and result['trip_matches']


@pytest.mark.parametrize('trip', [
    '2099/01/16 台北 台中 09:31 117', '2099/01/15 台中 台北 09:31 117',
    '2099/01/15 台北 左營 09:31 117', '2099/01/15 台北 台中 09:31 118', '2099/01/15 台北 台中 10:31 117'])
def test_trip_mismatch_does_not_enable_cancel(trip):
    assert not parse_official(page(trip=trip), CODE, TRIP)['trip_matches']


def test_two_legs_and_help_text_are_not_single_trip_proof():
    html = page() + '<table><tr><td>2099/01/16 台中 台北 08:00 0118</td></tr></table>'
    assert not parse_official(html, CODE, TRIP)['trip_matches']
    html = page(trip='2099/01/15 台中 左營 09:31 10:18 117') + '<footer>台北 台中</footer>'
    assert not parse_official(html, CODE, TRIP)['trip_matches']


def test_footer_date_cannot_validate_a_different_trip_date():
    html = page(trip='2099/01/16 台北 台中 09:31 10:18 117') + '<footer>2099/01/15</footer>'
    assert not parse_official(html, CODE, TRIP)['trip_matches']


def test_day_number_cannot_substitute_for_train_number():
    expected = {**TRIP, 'date': '2099-01-17', 'train_id': '0017'}
    assert not parse_official(page(trip='2099/01/17 台北 台中 09:31 10:18 118'), CODE, expected)['trip_matches']


def test_arrival_time_cannot_substitute_for_departure_time():
    assert not parse_official(page(trip='2099/01/15 台北 台中 08:30 09:31 117'), CODE, TRIP)['trip_matches']


@pytest.mark.parametrize('trip', [
    '2099/02/30 台北 台中 09:31 10:18 117', '2099/01/15 台北 台中 25:00 10:18 117',
    '2099/01/15 台北 台中 09:31 10:18 117 700', '2099/01/15 台北 台中 09:31 10:18 0000'])
def test_invalid_or_ambiguous_cells_do_not_enable_cancel(trip):
    assert not parse_official(page(trip=trip), CODE, TRIP)['trip_matches']


@pytest.mark.parametrize('html', [
    page(code='87654321'), page(status='未知'), '<form id="HistoryForm"></form>',
    '<p>訂位代號 12345678 未付款 2099/01/15 台北 台中 117</p>',
    page() + '<table><tr><th>交易狀態</th><td>已付款</td></tr></table>'])
def test_ambiguous_or_rejected_page_preserves_uncertainty(html):
    with pytest.raises(StorageError):
        parse_official(html, CODE, TRIP)


def evidence(tmp_path, pending=False):
    config = tmp_path / 'booking.json'
    config.write_text('{}')
    state, _ = record_paths(config)
    atomic_json(state, {'_record_version': 1, 'status': 'submission_pending' if pending else 'booked',
                        'booking_codes': [CODE]})
    return OfficialEvidence(config, CODE, pending_fingerprint(config))


def test_sync_pending_retains_guard_and_changes_fingerprint(tmp_path):
    item = evidence(tmp_path, pending=True)
    before = item.fingerprint
    item.sync(parse_official(page(), CODE, TRIP))
    assert item.check()['status'] == 'booked'
    assert item.fingerprint != before and item.state.exists()
    assert item.check()['official_status'] == 'unpaid'


def test_cancel_intent_durable_and_success_archives_original(tmp_path):
    item = evidence(tmp_path)
    original = item.state.read_bytes()
    item.prepare_cancel(parse_official(page(), CODE, TRIP))
    assert json.loads(item.path.read_text(encoding='utf-8'))['status'] == 'cancellation_pending'
    assert item.state.read_bytes() == original
    archive = item.cancel_success(parse_official(page('已取消'), CODE, TRIP))
    assert not item.state.exists() and (archive / 'state.json').read_bytes() == original
    assert json.loads((archive / 'resolution.json').read_text(encoding='utf-8'))['source'] == 'official_response'


@pytest.mark.parametrize('status', ['已付款', '已取票', '已取消'])
def test_non_unpaid_cancellation_is_blocked(tmp_path, status):
    item = evidence(tmp_path)
    with pytest.raises(StorageError):
        item.prepare_cancel(parse_official(page(status), CODE, TRIP))
    assert item.state.exists() and not item.path.exists()


def test_stale_state_and_failed_intent_write_never_release_guard(tmp_path, monkeypatch):
    item = evidence(tmp_path)
    atomic_json(item.state, {'status': 'booked', 'booking_codes': ['87654321']})
    with pytest.raises(StorageError):
        item.prepare_cancel(parse_official(page(), CODE, TRIP))
    item = evidence(tmp_path)
    monkeypatch.setattr('thsr_ticket.official_booking.atomic_json', lambda *a: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        item.prepare_cancel(parse_official(page(), CODE, TRIP))
    assert item.state.exists()

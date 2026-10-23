"""Strict official-page snapshots and durable query/cancellation evidence."""
import re
from datetime import date as calendar_date
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup
from thsr_ticket.backup import safe_path
from thsr_ticket.booking_records import record_paths, read_object, pending_fingerprint, booking_codes
from thsr_ticket.run_records import atomic_json, timestamp
from thsr_ticket.storage_errors import StorageError

HISTORY_URL = 'https://irs.thsrc.com.tw/IMINT/?wicket:bookmarkablePage=:tw.com.mitac.webapp.thsr.viewer.History'
STATIONS = ('南港', '台北', '板橋', '桃園', '新竹', '苗栗', '台中', '彰化', '雲林', '嘉義', '台南', '左營')
DATE_TOKEN = r'20\d{2}[/-]\d{1,2}[/-]\d{1,2}'


def canonical_date(value):
    if not isinstance(value, str) or not re.fullmatch(DATE_TOKEN, value):
        return ''
    try:
        return calendar_date(*map(int, re.split('[/-]', value))).isoformat()
    except ValueError:
        return ''


def trip_fields(row):
    """One leaf row, six separate cells; never borrow dates, times or numbers from elsewhere."""
    cells = [cell.get_text(' ', strip=True) for cell in row.find_all(['td', 'th'], recursive=False)]
    if len(cells) != 6:
        return {}
    day, start, destination, departure, arrival, train = cells
    day = canonical_date(day)
    if (not day or start not in STATIONS or destination not in STATIONS or start == destination
            or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', departure)
            or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', arrival)
            or not re.fullmatch(r'\d{1,4}', train) or int(train) == 0):
        return {}
    return {'date': day, 'start_station': start, 'dest_station': destination, 'depart_time': departure,
            'arrival_time': arrival, 'train_id': str(int(train)).zfill(4)}


def labelled(soup, labels):
    values = []
    for element in soup.find_all(['th', 'td', 'dt', 'span', 'label', 'strong', 'p']):
        text = element.get_text(' ', strip=True).rstrip('：:').strip()
        if text not in labels:
            continue
        sibling = element.find_next_sibling()
        if sibling is None and element.parent and element.parent.name in ('th', 'td'):
            sibling = element.parent.find_next_sibling()
        if sibling:
            value = sibling.get_text(' ', strip=True)
            if 0 < len(value) <= 100:
                values.append(value)
    return values


def parse_official(html, code, expected=None):
    if not re.fullmatch('[0-9]{8}', code) or len(html) > 2 * 1024 * 1024:
        raise StorageError('official_unrecognized')
    soup = BeautifulSoup(html, 'html.parser')
    if soup.find('form', id='HistoryForm'):
        raise StorageError('official_query_rejected')
    codes = labelled(soup, {'訂位代號', '訂位代碼'})
    if not codes or any(not re.fullmatch(r'\s*' + code + r'\s*', item) for item in codes):
        raise StorageError('official_mismatch')
    statuses = labelled(soup, {'付款狀態', '交易狀態', '訂位狀態'})
    status = 'unknown'
    if any(value in ('已取消', '訂位已取消', '取消成功', '已退票') for value in statuses):
        status = 'cancelled'
    elif any(value in ('已取票', '已出票') for value in statuses):
        status = 'collected'
    elif any(value in ('未付款', '尚未付款', '待付款') for value in statuses):
        status = 'unpaid'
    elif any(value in ('已付款', '付款完成') for value in statuses):
        status = 'paid'
    if status == 'unknown':
        raise StorageError('official_unrecognized')
    if (any(value in ('未付款', '尚未付款', '待付款') for value in statuses)
            and any(value in ('已付款', '付款完成', '已取票', '已出票', '已取消', '已退票') for value in statuses)):
        raise StorageError('official_unrecognized')
    expected = dict(expected or {})
    date = canonical_date(expected.get('date'))
    train = str(expected.get('train_id', '')).lstrip('0')
    station_values = [expected.get('start_station'), expected.get('dest_station')]
    trip_rows = [row for row in soup.find_all('tr') if row.find('tr') is None
                 and re.search(DATE_TOKEN, row.get_text(' ', strip=True))
                 and sum(station in row.get_text() for station in STATIONS) >= 2]
    actual = trip_fields(trip_rows[0]) if len(trip_rows) == 1 else {}
    matches = (bool(date and train and all(station_values) and actual) and actual['date'] == date
               and actual['start_station'] == station_values[0] and actual['dest_station'] == station_values[1]
               and actual['train_id'].lstrip('0') == train
               and all(not expected.get(key) or expected[key] == actual[key]
                       for key in ('depart_time', 'arrival_time')))
    return {'code': code, 'status': status, 'verified_at': timestamp(), 'trip_matches': bool(matches),
            'ticket': actual if matches else {key: str(expected.get(key, '')) for key in
                                              ('date', 'start_station', 'dest_station', 'train_id',
                                               'depart_time', 'arrival_time')},
            'source': 'official_page'}


class OfficialEvidence:
    """Caller holds record_lock for the entire browser session."""
    def __init__(self, config, code, fingerprint):
        self.config, self.code, self.fingerprint = Path(config), code, fingerprint
        self.state, runs = record_paths(config)
        self.folder = safe_path(runs / 'official')
        self.path = self.folder / (uuid4().hex + '.json')
        self.data = {'_record_version': 1, 'code': code, 'created_at': timestamp(), 'status': 'query_started'}

    def check(self):
        safe_path(self.state)
        if pending_fingerprint(self.config) != self.fingerprint:
            raise StorageError('records_changed')
        value = read_object(self.state)
        if value.get('status') == 'booked':
            if booking_codes(value) != [self.code]:
                raise StorageError('official_mismatch')
        elif value.get('status') != 'submission_pending':
            raise StorageError('official_mismatch')
        return value

    def save(self, status, snapshot=None):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.data = {**self.data, 'status': status, 'updated_at': timestamp()}
        if snapshot is not None:
            self.data['snapshot'] = snapshot
        atomic_json(self.path, self.data)

    def sync(self, snapshot):
        current = self.check()
        if (snapshot['code'] != self.code or not snapshot['trip_matches']
                or snapshot['status'] not in ('unpaid', 'paid')):
            raise StorageError('official_mismatch')
        self.save('query_verified', snapshot)
        stored_ticket = current.get('ticket') if isinstance(current.get('ticket'), dict) else {}
        atomic_json(self.state, {**current, '_record_version': 1, 'status': 'booked', 'booking_codes': [self.code],
                                 'ticket': {**snapshot['ticket'], **stored_ticket},
                                 'outbound_date': snapshot['ticket'].get('date', ''),
                                 'source': 'official_query', 'official_status': snapshot['status'],
                                 'verified_at': snapshot['verified_at']})
        self.fingerprint = pending_fingerprint(self.config)
        return self.fingerprint

    def prepare_cancel(self, snapshot):
        self.check()
        if snapshot['code'] != self.code or snapshot['status'] != 'unpaid' or not snapshot['trip_matches']:
            raise StorageError('official_cancel_unavailable')
        self.save('cancellation_pending', snapshot)  # Must succeed before the irreversible click.

    def cancel_success(self, snapshot):
        self.check()
        if snapshot['code'] != self.code or snapshot['status'] != 'cancelled':
            raise StorageError('official_unconfirmed')
        self.save('cancelled', snapshot)
        _, runs = record_paths(self.config)
        directory = safe_path(runs / 'archives' / uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        atomic_json(directory / 'resolution.json', {
            '_record_version': 1, 'source': 'official_response', 'outcome': 'cancelled',
            'confirmed_at': snapshot['verified_at'], 'booking_code': self.code,
        })
        self.state.rename(directory / 'state.json')
        return directory

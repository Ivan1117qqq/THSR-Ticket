"""Inspect and archive local records without reading personal config or connecting."""
import json
import hashlib
import builtins
from functools import partial
from pathlib import Path
from uuid import uuid4

from thsr_ticket.run_records import timestamp, atomic_json
from thsr_ticket.record_lock import record_lock


def record_paths(config_path):
    state = Path(config_path).resolve().with_suffix('.state.json')
    runs = state.parent / (state.name.removesuffix('.state.json') + '.runs')
    return state, runs


def read_object(path):
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('紀錄格式必須是 JSON 物件。')
    return value


def booking_codes(value):
    codes = value.get('booking_codes')
    if not isinstance(codes, list) or not codes or any(not isinstance(code, str) or not code.strip() for code in codes):
        raise ValueError('紀錄沒有有效的訂位代碼，不能自動封存。')
    return [code.strip() for code in codes]


def show_bookings(config_path, output=None):
    print = partial(builtins.print, file=output)
    state, runs = record_paths(config_path)
    print('以下為本機紀錄，不會同步官網付款或取消狀態。')
    if state.exists():
        try:
            data = read_object(state)
            if data.get('status') == 'booked':
                print('目前防重送紀錄：已訂位；代碼 ' + '、'.join(booking_codes(data)))
            elif data.get('status') == 'submission_pending':
                print('目前防重送紀錄：訂位結果待確認，請先至官網查詢；不可自動封存。')
            else:
                print('目前防重送紀錄：未知狀態，請人工確認。')
        except (ValueError, OSError):
            print('目前防重送紀錄無法讀取；防重送阻擋仍保留，請人工確認。')
        print(f'狀態檔：{state}')
    else:
        print('目前沒有防重送紀錄；這不代表官網沒有既有訂位。')

    found = False
    for path in sorted(runs.glob('*/result.json')):
        found = True
        try:
            data = read_object(path)
            tickets = data.get('tickets')
            if not isinstance(tickets, list) or not tickets or not all(isinstance(t, dict) for t in tickets):
                raise ValueError('缺少訂位結果。')
            print(f'\n完整結果：{path}')
            print(f'保存時間：{data.get("saved_at", "未記錄")}（訂位當時尚未付款）')
            for ticket in tickets:
                # Display only known result fields, not arbitrary JSON properties.
                fields = [('id', '訂位代碼'), ('date', '日期'), ('start_station', '起站'),
                          ('dest_station', '迄站'), ('train_id', '車次'), ('depart_time', '出發'),
                          ('arrival_time', '抵達'), ('seat_class', '車廂'), ('seat', '座位'),
                          ('ticket_num_info', '票數'), ('price', '金額'), ('payment_deadline', '繳費期限')]
                for key, label in fields:
                    print(f'  {label}：{ticket.get(key, "未記錄")}')
        except (ValueError, OSError):
            print(f'無法讀取完整結果，略過：{path}')

    for path in sorted(runs.glob('archives/*/state.json')):
        found = True
        try:
            print('\n已封存：' + '、'.join(booking_codes(read_object(path))))
            print(f'封存檔：{path}')
        except (ValueError, OSError):
            print(f'無法讀取封存紀錄，略過：{path}')
    if not found:
        print('尚無完整結果或封存檔；舊版本僅保存代碼時，無法補回完整行程。')


def archive_booking(config_path, expected_code, output=None):
    state, _ = record_paths(config_path)
    with record_lock(state):
        return _archive_booking(config_path, expected_code, output)


def _archive_booking(config_path, expected_code, output=None):
    print = partial(builtins.print, file=output)
    state, runs = record_paths(config_path)
    # A dedicated lock serializes archive commands. Booking cannot pass the existing state marker.
    lock = state.with_suffix('.archive.lock')
    acquired = False
    try:
        with lock.open('x', encoding='utf-8') as handle:
            acquired = True
            handle.write(timestamp())
        if not state.exists():
            raise ValueError('沒有可封存的防重送紀錄。')
        data = read_object(state)
        if data.get('status') != 'booked':
            raise ValueError('只有已成功訂位的紀錄可自動封存；待確認或未知狀態請先至官網確認。')
        if expected_code.strip() not in booking_codes(data):
            raise ValueError('輸入的訂位代碼與目前紀錄不符，未封存。')
        # Resolve and verify the destination stays in this config's record directory.
        root = runs.resolve()
        archive = root / 'archives' / uuid4().hex
        destination = archive / 'state.json'
        if not destination.resolve().is_relative_to(root):
            raise ValueError('封存路徑超出紀錄目錄。')
        archive.mkdir(parents=True, exist_ok=False)
        try:
            state.rename(destination)
        except OSError:
            archive.rmdir()  # Only the empty directory created above, never recursive deletion.
            raise
        print(f'已封存：{destination}')
        print('原官網訂位仍然存在；請更新行程設定，再自行執行下一筆訂位。')
        return destination
    finally:
        if acquired:
            lock.unlink()


def pending_fingerprint(config_path):
    state, _ = record_paths(config_path)
    return hashlib.sha256(state.read_bytes()).hexdigest()


def resolve_pending(config_path, outcome, expected_fingerprint, confirmed=False, code=''):
    """Archive uncertain local state only after explicit manual verification; no website mutation."""
    if not confirmed or outcome not in ('booked', 'not_booked', 'cancelled'):
        raise ValueError('請先核對官網訂位結果，再選擇確認結果。')
    if outcome == 'booked' and not code.strip():
        raise ValueError('確認已訂位時請填入官網顯示的訂位代碼。')
    state, runs = record_paths(config_path)
    with record_lock(state):
        if pending_fingerprint(config_path) != expected_fingerprint:
            raise ValueError('紀錄已變更，請重新整理後再確認。')
        data = read_object(state)
        if data.get('status') != 'submission_pending':
            raise ValueError('此操作只適用結果待確認的紀錄。')
        directory = runs / 'archives' / uuid4().hex
        if not directory.resolve().is_relative_to(runs.resolve()):
            raise ValueError('封存路徑超出紀錄目錄。')
        directory.mkdir(parents=True, exist_ok=False)
        atomic_json(directory / 'resolution.json', {
            'confirmed_at': timestamp(), 'source': 'user_verified', 'outcome': outcome,
            'booking_code': code.strip() if outcome == 'booked' else '',
        })
        # Original bytes are kept. If the rename fails, the blocking state remains.
        state.rename(directory / 'state.json')
        return directory


def record_entries(config_path):
    """Structured view for the desktop; never includes passenger credentials."""
    state, runs = record_paths(config_path)
    entries = []
    active_codes = []
    if state.exists():
        try:
            current = read_object(state)
            if current.get('status') == 'booked':
                active_codes = booking_codes(current)
                for code in active_codes:
                    entries.append({'status': 'booked', 'code': code, 'current': True, 'ticket': {},
                                    'fingerprint': pending_fingerprint(config_path)})
            else:
                entries.append({'status': current.get('status', 'unknown'), 'code': '', 'current': True,
                                'ticket': {'date': str(current.get('outbound_date', '—')),
                                           'train_id': str(current.get('train_id', '—'))},
                                'fingerprint': pending_fingerprint(config_path)})
        except (ValueError, OSError):
            entries.append({'status': 'unreadable', 'code': '', 'current': True, 'ticket': {}})
    for path in sorted(runs.glob('*/result.json'), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            data = read_object(path)
            for ticket in data.get('tickets', []):
                if not isinstance(ticket, dict) or not ticket.get('id'):
                    continue
                match = next((item for item in entries if item['code'] == ticket['id']), None)
                if match is None:
                    match = {'status': 'history', 'code': ticket['id'], 'current': False, 'ticket': {}}
                    entries.append(match)
                if not match['ticket']:
                    match['ticket'] = {key: str(ticket.get(key, '')) for key in (
                        'date', 'start_station', 'dest_station', 'train_id', 'depart_time', 'arrival_time',
                        'seat', 'seat_class', 'price', 'payment_deadline', 'ticket_num_info')}
        except (ValueError, OSError, TypeError):
            continue
    for path in sorted(runs.glob('archives/*/state.json')):
        try:
            data = read_object(path)
            codes = data.get('booking_codes', [])
            resolution = path.parent / 'resolution.json'
            if resolution.exists():
                resolved = read_object(resolution)
                code = resolved.get('booking_code', '')
                if code and resolved.get('outcome') == 'cancelled':
                    match = next((item for item in entries if item['code'] == code and not item['current']), None)
                    if match is not None:
                        match.update(status='resolved', resolution='cancelled',
                                     confirmed_at=resolved.get('confirmed_at', ''))
                        continue
                entries.append({'status': 'resolved', 'code': code, 'current': False,
                                'ticket': {'date': str(data.get('outbound_date', '')),
                                           'train_id': str(data.get('train_id', ''))},
                                'resolution': resolved.get('outcome', ''),
                                'confirmed_at': resolved.get('confirmed_at', '')})
            else:
                for code in codes:
                    if not any(item['code'] == code for item in entries):
                        entries.append({'status': 'history', 'code': code, 'current': False, 'ticket': {}})
        except (ValueError, OSError, TypeError):
            continue
    return entries


def confirm_cancelled(config_path, code, fingerprint, confirmed=False):
    """Record the user's completed official cancellation; this does not cancel a ticket itself."""
    if not confirmed:
        raise ValueError('請先確認官網已顯示取消成功。')
    state, runs = record_paths(config_path)
    with record_lock(state):
        if pending_fingerprint(config_path) != fingerprint:
            raise ValueError('紀錄已變更，請重新整理。')
        data = read_object(state)
        if data.get('status') != 'booked' or booking_codes(data) != [code]:
            raise ValueError('只能處理目前單筆已訂位紀錄。')
        directory = runs / 'archives' / uuid4().hex
        if not directory.resolve().is_relative_to(runs.resolve()):
            raise ValueError('封存路徑超出紀錄目錄。')
        directory.mkdir(parents=True, exist_ok=False)
        atomic_json(directory / 'resolution.json', {
            'confirmed_at': timestamp(), 'source': 'user_verified',
            'outcome': 'cancelled', 'booking_code': code,
        })
        state.rename(directory / 'state.json')
        return directory

"""Inspect and archive local records without reading personal config or connecting."""
import json
from pathlib import Path
from uuid import uuid4

from thsr_ticket.run_records import timestamp


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


def show_bookings(config_path):
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


def archive_booking(config_path, expected_code):
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

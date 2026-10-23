"""Isolated manual review with generated local records; real booking actions are blocked."""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from thsr_ticket.run_records import atomic_json
from thsr_ticket.storage_errors import StorageError


def create_review_data(directory):
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    config = {'_schema_version': 1, 'start_at': '2099-01-15T08:00:00+08:00',
              'outbound_date': '2099-01-15', 'start_station': 2, 'dest_station': 7,
              'personal_id': 'DEMO-NOT-A-PERSON', 'phone_num': '', 'max_attempts': 60}
    for name in ('booked', 'pending', 'logs', 'backup'):
        (root / name).mkdir()
        atomic_json(root / name / 'booking.local.json', config)
    booked = root / 'booked'
    ticket = {'id': 'DEMO0001', 'date': '2099-01-15', 'start_station': '台北', 'dest_station': '台中',
              'train_id': '0117', 'depart_time': '09:31', 'arrival_time': '10:18',
              'seat': '示範 9 車 3E', 'seat_class': '標準', 'price': 'TWD 700（假資料）',
              'payment_deadline': '示範期限', 'ticket_num_info': '成人 1 張'}
    for name in ('booked', 'backup'):
        atomic_json(root / name / 'booking.local.state.json', {
            '_record_version': 1, 'status': 'booked', 'booking_codes': ['DEMO0001'],
            'outbound_date': '2099-01-15', 'ticket': ticket})
    for number in range(1, 32):
        directory = booked / 'booking.local.runs' / f'{number:032x}'
        directory.mkdir(parents=True)
        atomic_json(directory / 'result.json', {
            '_record_version': 1, 'saved_at': '2099-01-15T08:00:00+08:00',
            'requested_outbound_date': '2099-01-15',
            'tickets': [{**ticket, 'id': f'DEMO{number:04d}'}]})
    atomic_json(root / 'pending/booking.local.state.json', {
        '_record_version': 1, 'status': 'submission_pending', 'outbound_date': '2099-01-15',
        'start_station': 2, 'dest_station': 7, 'train_id': 117})
    for number in range(1, 4):
        directory = root / 'logs/booking.local.runs' / f'{number:032x}'
        directory.mkdir(parents=True)
        events = directory / 'events.jsonl'
        events.write_text(json.dumps({'_record_version': 1, 'event': 'run_started', 'query_only': True}) + '\n' +
                          json.dumps({'_record_version': 1, 'event': 'run_finished'}) + '\n', encoding='utf-8')
        os.utime(events, (946684800, 946684800))
    manifest = {'version': 1, 'synthetic': True, 'booked_records': 31,
                'query_logs': 3, 'cases': ['booked', 'pending', 'logs', 'backup']}
    atomic_json(root / 'review-data.json', manifest)
    (root / 'README.txt').write_text(
        '這是可重建的驗收假資料，不是真實訂位。\n'
        'booked：已訂位與 30 筆歷史；pending：結果待確認；logs：3 筆過期純查票日誌。\n'
        'backup：獨立的已訂位副本，供備份／還原驗收，不受 booked 封存操作影響。\n'
        '請使用 python -m scripts.review_desktop --data 本資料夾 開啟隔離驗收視窗。\n'
        '假證號刻意無效；不可拿這些代碼查詢官網。\n', encoding='utf-8')
    return root


def review_controller(directory):
    from PySide6.QtCore import Slot
    from thsr_ticket.desktop.controller import DesktopController

    root = Path(directory).resolve()
    manifest = json.loads((root / 'review-data.json').read_text(encoding='utf-8'))
    if manifest.get('version') != 1 or manifest.get('synthetic') is not True:
        raise ValueError('請選擇本工具建立的驗收資料夾。')

    class ReviewController(DesktopController):
        @Slot(bool)
        def start(self, query_only):
            self.notify('目前為假資料驗收模式；查票與自動訂位已停用。', True)

        @Slot()
        def official(self):
            self.notify('假資料不能查詢官網；實站驗收請另開正式程式。', True)

        @Slot(str)
        def openCancellation(self, code):
            self.official()

        def load_path(self, path):
            if not Path(path).resolve().is_relative_to(root):
                self.notify('驗收視窗只接受本次假資料資料夾內的設定。', True)
                return False
            return super().load_path(path)

        def save_config(self):
            if not self.path.resolve().is_relative_to(root):
                raise ValueError('驗收設定只能儲存在假資料資料夾。')
            return super().save_config()

    # Every review launch gets fresh preferences; never open the real AppData or last_config.
    controller = ReviewController(root / 'ui-sessions' / uuid4().hex)

    def no_browser():
        raise StorageError('official_cancel_unavailable')

    controller.management.factory = no_browser
    return controller


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', help='Existing generated review-data directory')
    parser.add_argument('--case', choices=('booked', 'pending', 'logs', 'backup'), default='booked')
    parser.add_argument('--scale', choices=('1', '1.25', '1.5'), default='1')
    args = parser.parse_args()
    os.environ['QT_SCALE_FACTOR'] = args.scale
    root = Path(args.data).resolve() if args.data else create_review_data(Path('build') / ('review-' + uuid4().hex))
    print('Review data: ' + str(root), flush=True)
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle
    from shiboken6 import delete
    from thsr_ticket.desktop.notifications import DesktopNotifications
    from thsr_ticket.desktop.single_instance import activate_window

    QQuickStyle.setStyle('Basic')
    app = QApplication([])
    base = Path(__file__).resolve().parents[1] / 'thsr_ticket/desktop'
    app.setWindowIcon(QIcon(str(base / 'assets/app.svg')))
    controller = review_controller(root)
    if not controller.load_path(root / args.case / 'booking.local.json'):
        raise SystemExit('Review config did not load')
    controller.navigate(3 if args.case != 'logs' else 4)
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({'backend': controller})
    engine.load(QUrl.fromLocalFile(str(base / 'qml/Main.qml')))
    if not engine.rootObjects():
        controller._record_loader.cancel()
        if controller._record_loader._thread is not None:
            controller._record_loader._thread.join()
        raise SystemExit('Review QML did not load')
    window = engine.rootObjects()[0]
    window.setTitle('Travel Desk · 假資料驗收（不會查票或訂位）')
    notifications = DesktopNotifications(app.windowIcon(), app)
    controller.tools.set_notification_support(notifications.available)
    controller.tools.notificationsChanged.connect(notifications.set_enabled)
    controller.tools.desktopNotification.connect(notifications.publish)
    notifications.opened.connect(lambda target: (controller.openNotification(target), activate_window(window)))
    controller.closeReady.connect(app.quit)
    try:
        app.exec()
    finally:
        notifications.set_enabled(False)
        controller.timer.stop()
        controller.storage._timer.stop()
        delete(engine)


if __name__ == '__main__':
    main()

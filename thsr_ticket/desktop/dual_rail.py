"""Qt coordinator for two independent booking jobs and a private-data-free TRA form."""
import json
import re
import threading
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication

from thsr_ticket.dual_rail import DualRailSession, thsr_job
from thsr_ticket.tra_booking import TraOptions, TraRecords, run_tra, stations, RECORD_URL
from thsr_ticket.run_records import atomic_json


class DualRailController(QObject):
    changed = Signal()
    formChanged = Signal()
    resetSecrets = Signal()
    finished = Signal()

    def __init__(self, directory, context, prepare, worker, parent=None, tra_worker=run_tra, prepare_tra=None):
        super().__init__(parent)
        self.directory = Path(directory)
        self.preferences = self.directory / 'dual-rail.preferences.json'
        self.records = TraRecords(directory)
        self.context, self.prepare, self.worker, self.tra_worker = context, prepare, worker, tra_worker
        self.prepare_tra = prepare_tra or prepare
        self.session = None
        self.network_enabled = True
        self._focus = threading.Event()
        self._known_code = ''
        self._events = []
        self._busy, self._message = False, '高鐵與台鐵各訂到一筆後，各自停止；不付款。'
        self._form = {key: str(value) for key, value in asdict(TraOptions('臺北', '臺中')).items()}
        self._rows = [{'operator': key, 'status': 'ready', 'message': '尚未啟動', 'attempt': 0}
                      for key in ('thsr', 'tra')]
        self._record = {}
        self._preferences_valid = True
        self.read_preferences()
        self.refresh_record()

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=changed)
    def hasSession(self):
        return self.session is not None

    @Property(bool, notify=changed)
    def running(self):
        return self._busy or self.context()['running']

    @Property('QVariantMap', notify=formChanged)
    def form(self):
        return dict(self._form)

    @Property('QVariantMap', constant=True)
    def issues(self):
        return {}

    @Property('QVariantList', constant=True)
    def stations(self):
        return list(stations())

    @Property('QVariantList', constant=True)
    def times(self):
        return [f'{hour:02d}:{minute:02d}' for hour in range(24) for minute in (0, 30)] + ['23:59']

    @Property(str, notify=changed)
    def events(self):
        return '\n'.join(self._events)

    @Property('QVariantList', notify=changed)
    def jobs(self):
        return [dict(row) for row in self._rows]

    @Property('QVariantMap', notify=changed)
    def record(self):
        return dict(self._record)

    @Property(str, notify=changed)
    def message(self):
        return self._message

    def notice(self, message):
        self._message = message
        self.changed.emit()

    def options(self):
        return TraOptions(**{**self._form, 'quantity': int(self._form['quantity']),
                             'max_attempts': int(self._form['max_attempts']),
                             'interval_seconds': float(self._form['interval_seconds']),
                             'network_failure_limit': int(self._form['network_failure_limit']),
                             'max_network_delay_seconds': float(self._form['max_network_delay_seconds'])})

    def stored_options(self):
        if self.preferences.is_symlink() or self.preferences.stat().st_size > 16384:
            raise ValueError()
        data = json.loads(self.preferences.read_text(encoding='utf-8'))
        if set(data) != {'version', 'tra'} or type(data['version']) is not int or data['version'] != 1:
            raise ValueError()
        return TraOptions(**data['tra'])

    def read_preferences(self):
        if not self.preferences.exists() and not self.preferences.is_symlink():
            return
        try:
            options = self.stored_options()
            self._form = {key: str(value) for key, value in asdict(options).items()}
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            self._preferences_valid = False
            self._message = '雙鐵設定無法讀取，原檔保留；請先備份並檢查 dual-rail.preferences.json。'

    @Slot(str, str)
    def setField(self, key, value):
        if not self.running and key in self._form and len(value) <= 120:
            self._form[key] = value
            self.formChanged.emit()

    @Slot(result=bool)
    def save(self):
        if self.running or not self._preferences_valid:
            return False
        try:
            options = self.options()
            if self.preferences.exists() or self.preferences.is_symlink():
                self.stored_options()  # Do not overwrite a file changed to an unknown version while App is open.
            self.directory.mkdir(parents=True, exist_ok=True)
            atomic_json(self.preferences, {'version': 1, 'tra': asdict(options)})
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            self.notice('台鐵設定未儲存；請檢查站別、半小時時段、票數、車次及重查設定。')
            return False
        self.notice('台鐵設定已保存；日期、啟動時間與證件使用目前高鐵行程表單。')
        return True

    @Slot(result=bool)
    def start(self):
        return self.begin(False)

    @Slot(result=bool)
    def startTra(self):
        return self.begin(True)

    @Slot(result=bool)
    def previewTra(self):
        return self.begin(True, True)

    def begin(self, tra_only, prefill_only=False):
        if self.running:
            return False
        if not self.network_enabled:
            self.notice('假資料驗收不會啟動瀏覽器、查票或訂位。')
            return False
        if self.records.path.exists() or self.records.path.is_symlink():
            self.refresh_record()
            self.notice('請先核對並封存目前台鐵紀錄；本次未啟動。')
            return False
        if not self.save():
            return False
        try:
            options = self.options()
            config, path = (self.prepare_tra if tra_only else self.prepare)()
        except (OSError, ValueError):
            self.notice('請先修正主表單的日期、啟動時間、證件與必要欄位；台鐵未啟動。' if tra_only else
                        '請先修正高鐵行程，或到「我的訂位」核對既有高鐵紀錄；兩邊均未啟動。')
            return False

        def tra_job(stop, emit):
            self.tra_worker(config, options, self.directory, stop, emit, focus_event=self._focus,
                            prefill_only=prefill_only)

        self._focus.clear()
        self._known_code = ''
        self._events = []
        jobs = {'tra': tra_job} if tra_only else {'thsr': thsr_job(config, path, self.worker), 'tra': tra_job}
        self.session = DualRailSession(jobs)
        self._busy = True
        self.session.start()
        self.update_rows()
        if prefill_only:
            self.notice('只檢查台鐵預填內容；不會自動送出，台鐵主頁導覽 POST 也會阻擋。')
        else:
            self.notice(('只啟動台鐵，高鐵未啟動。' if tra_only else '雙鐵已啟動。')
                        + '台鐵出現驗證或後續選擇時，請在獨立 Chrome 完成。')
        return True

    def update_rows(self):
        self._rows = [dict(self.session.rows.get(key, {'operator': key, 'status': 'idle',
                                                       'message': '本次未啟動', 'attempt': 0}))
                      for key in ('thsr', 'tra')]

    @Slot()
    def focusTra(self):
        if self._busy and self.session and 'tra' in self.session.threads:
            if self.session.threads['tra'].is_alive():
                self._focus.set()

    @Slot()
    def copyCode(self):
        code = self._record.get('booking_code', '')
        if re.fullmatch(r'[0-9A-Z]{6,12}', str(code)):
            QGuiApplication.clipboard().setText(code)
            self.notice('已複製台鐵訂票代碼。')

    @Slot(str)
    def stop(self, operator=''):
        if self.session and (not operator or operator in ('thsr', 'tra')):
            self.session.stop(operator or None)
            self.notice('正在停止指定工作；已送出的訂位保留，停止不等於取消車票。')

    def poll(self):
        if not self._busy or self.session is None:
            return
        if self.session.poll():
            self.update_rows()
            tra = self.session.rows.get('tra', {})
            self._known_code = tra.get('booking_code', '')
            if tra.get('status') in ('booked', 'pending'):
                self.refresh_record()
            for row in self._rows:
                line = ('高鐵' if row['operator'] == 'thsr' else '台鐵') + '：' + row['message']
                if not self._events or line not in self._events[-2:]:
                    self._events.append(line)
            self._events = self._events[-80:]
            self.changed.emit()
        if not self.session.busy:
            self.session.poll()
            self.update_rows()
            self._known_code = self.session.rows.get('tra', {}).get('booking_code', '')
            self._busy = False
            self.refresh_record()
            self.notice('訂票工作已結束，請確認各筆結果；不要的車票請自行至官網取消。')
            self.finished.emit()

    @Slot()
    def refresh_record(self):
        if not self.records.path.exists() and not self.records.path.is_symlink():
            self._record = {}
        else:
            try:
                value = self.records.read()
                self._record = {key: value.get(key, '') for key in (
                    'status', 'booking_code', 'outbound_date', 'start_station', 'dest_station', 'quantity')}
                if self._known_code and not self._record['booking_code']:
                    self._record.update(booking_code=self._known_code, save_failed=True)
            except (ValueError, OSError, AttributeError):
                self._record = {'status': 'unreadable'}
        self.changed.emit()

    @Slot(bool, result=bool)
    def archive(self, confirmed):
        if self.running or not confirmed:
            return False
        try:
            self.records.archive()
        except (OSError, ValueError, RuntimeError, KeyError, AttributeError):
            self.notice('無法封存台鐵紀錄，原檔保留；請先確認官網狀態。')
            return False
        self.refresh_record()
        self._known_code = ''
        self.notice('台鐵本機紀錄已封存，官網訂位仍保留；下次可重新執行。')
        return True

    @Slot(str, bool, result=bool)
    def confirmResult(self, code, confirmed):
        code = code.strip().upper()
        if self.running or not confirmed or not re.fullmatch(r'[0-9A-Z]{6,12}', code):
            self.notice('請先在官網確認訂位成功，再輸入正確訂票代碼並勾選確認。')
            return False
        try:
            from thsr_ticket.record_lock import record_lock
            with record_lock(self.records.path):
                if self.records.read()['status'] != 'pending':
                    return False
                self.records.booked({'booking_code': code, 'source': 'user_confirmed'})
        except (OSError, ValueError, RuntimeError):
            self.notice('無法保存人工核對結果，原紀錄保留。')
            return False
        self.refresh_record()
        self.notice('已保存你在官網核對的台鐵訂票代碼；本機登記不會送出新的訂位。')
        return True

    @Slot()
    def official(self):
        if self.network_enabled:
            QDesktopServices.openUrl(QUrl(RECORD_URL))
        else:
            self.notice('假資料驗收不會開啟官網。')

    @Slot()
    def openLogs(self):
        path = self.directory / 'tra-booking.local.runs'
        if path.is_dir() and not path.is_symlink():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
        else:
            self.notice('尚無台鐵執行紀錄；啟動後會自動保存。')

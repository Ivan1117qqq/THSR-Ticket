"""Qt adapter: state and commands, with no network work on the UI thread."""
import io
import json
import queue
import threading
import importlib.util
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog
from pydantic import ValidationError

from thsr_ticket.application import STATIONS, FIELDS, form_config, protected_config_path, run_background
from thsr_ticket.automation import TAIPEI
from thsr_ticket.booking_records import record_entries, record_paths, archive_booking, resolve_pending
from thsr_ticket.run_records import atomic_json


def defaults():
    now = datetime.now(TAIPEI)
    return dict(start_at=now.strftime('%Y-%m-%d %H:%M:%S'), outbound_date=now.date().isoformat(),
                start_station='台北', dest_station='左營', earliest_departure='09:30', latest_departure='23:59',
                train_ids='', adult_tickets='1', child_tickets='0', disabled_tickets='0', elder_tickets='0',
                college_tickets='0', class_type='標準', personal_id='', phone_num='', interval_seconds='1',
                max_attempts='60', ocr_model='standard')


def form_values(data):
    if not isinstance(data, dict) or set(data) - {name for name, _ in FIELDS}:
        raise ValueError('請選擇訂票設定，不能載入狀態或結果檔。')
    result = defaults()
    for key, value in data.items():
        if key in ('start_station', 'dest_station'):
            if not isinstance(value, int) or not 1 <= value <= len(STATIONS):
                raise ValueError('車站設定無效。')
            value = STATIONS[value - 1]
        elif key == 'class_type':
            if value not in (0, 1):
                raise ValueError('車廂設定無效。')
            value = ['標準', '商務'][value]
        elif key == 'train_ids':
            if not isinstance(value, list):
                raise ValueError('車次設定無效。')
            value = ', '.join(map(str, value))
        elif key == 'start_at':
            dt = datetime.fromisoformat(str(value))
            value = (dt.replace(tzinfo=TAIPEI) if dt.tzinfo is None else dt.astimezone(TAIPEI))
            value = value.strftime('%Y-%m-%d %H:%M:%S')
        result[key] = str(value)
    return result


class DesktopController(QObject):
    changed = Signal()
    formChanged = Signal()
    closeReady = Signal()
    resetSecrets = Signal()

    def __init__(self, data_dir, worker=run_background):
        super().__init__()
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / 'booking.local.json'
        self.worker = worker
        self._form = defaults()
        self._records = []
        self._status = '設定行程，開始下一段旅程。'
        self._phase = '尚未開始'
        self._attempt = 0
        self._running = False
        self._page = 0
        self._log = ''
        self._error = False
        self._issues = {}
        self._match = {}
        self._countdown = ''
        self._closing = False
        self._thread = None
        self._received_done = False
        self._messages = queue.Queue()
        self._stop = threading.Event()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        if self.path.exists():
            self.load_path(self.path)

    @Property('QVariantMap', notify=formChanged)
    def form(self):
        return self._form

    @Property('QVariantMap', notify=changed)
    def issues(self):
        return self._issues

    @Property('QVariantMap', notify=changed)
    def match(self):
        return self._match

    @Property(str, notify=changed)
    def countdown(self):
        return self._countdown

    @Property('QStringList', constant=True)
    def stations(self):
        return STATIONS

    @Property('QVariantList', notify=changed)
    def records(self):
        return self._records

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def phase(self):
        return self._phase

    @Property(str, notify=changed)
    def log(self):
        return self._log

    @Property(str, notify=changed)
    def configPath(self):
        return str(self.path)

    @Property(bool, notify=changed)
    def running(self):
        return self._running

    @Property(bool, notify=changed)
    def error(self):
        return self._error

    @Property(int, notify=changed)
    def attempt(self):
        return self._attempt

    @Property(int, notify=changed)
    def page(self):
        return self._page

    def notify(self, text, error=False):
        self._status, self._error = text, error
        self.changed.emit()

    @Slot(int)
    def navigate(self, page):
        if 0 <= page <= 4:
            self._page = page
            if page == 3:
                self.refresh()
            self.changed.emit()

    @Slot(str, str)
    def setField(self, key, value):
        if not self._running and key in self._form:
            self._form[key] = value
            self.formChanged.emit()
            if key in self._issues:
                self._issues.pop(key)
                self.changed.emit()

    @Slot()
    def now(self):
        self.setField('start_at', datetime.now(TAIPEI).strftime('%Y-%m-%d %H:%M:%S'))

    @Slot()
    def swap(self):
        if not self._running:
            a, b = self._form['start_station'], self._form['dest_station']
            self._form.update(start_station=b, dest_station=a)
            self.formChanged.emit()

    def load_path(self, path):
        if self._running:
            return False
        try:
            new = form_values(json.loads(Path(path).read_text(encoding='utf-8-sig')))
            # Keep the original location: its state/runs guard must follow the setting.
            self.path = Path(path).resolve()
            self._form = new
            self.resetSecrets.emit()
            self.formChanged.emit()
            self.refresh()
            self.notify('已載入設定，請核對日期與時間。')
            return True
        except (ValueError, OSError, TypeError):
            self.notify('無法載入；請選擇有效的訂票設定 JSON。', True)
            return False

    @Slot()
    def load(self):
        if self._running:
            return
        path, _ = QFileDialog.getOpenFileName(None, '載入設定', str(self.path.parent), 'JSON (*.json)')
        if path:
            self.load_path(path)

    def save_config(self):
        self._issues = {}
        try:
            config = form_config({key: value.strip() for key, value in self._form.items()})
        except ValidationError as exc:
            for error in exc.errors():
                key = str(error['loc'][0])
                self._issues[key] = '請檢查格式與範圍。'
            self.changed.emit()
            raise
        if protected_config_path(self.path):
            raise ValueError('範本不能直接儲存，請先在設定頁另存個人設定。')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self.path, json.loads(config.json()))
        return config

    @Slot()
    def save(self):
        if self._running:
            return
        try:
            self.save_config()
            self.notify('設定已儲存。')
        except (ValueError, OSError):
            self.notify('儲存失敗：請檢查日期、時段、票數、身分證與儲存位置。', True)

    @Slot()
    def saveAs(self):
        if self._running:
            return
        # Do not detach the active state from its config by silently copying just JSON.
        if record_paths(self.path)[0].exists():
            self.notify('請先在「我的訂位」處理目前紀錄，再另存設定。', True)
            return
        target, _ = QFileDialog.getSaveFileName(
            None, '另存設定', str(self.data_dir / 'booking.local.json'), 'JSON (*.json)')
        if target:
            old = self.path
            self.path = Path(target)
            try:
                self.save_config()
            except (ValueError, OSError):
                self.path = old
                self.notify('另存失敗，未變更目前設定位置。', True)
                return
            self.refresh()
            self.notify('已另存設定。')

    @Slot(bool)
    def start(self, query_only):
        if self._running:
            return
        if not query_only and record_paths(self.path)[0].exists():
            self.navigate(3)
            self.notify('請先處理既有訂位紀錄；本次未啟動。', True)
            return
        try:
            config = self.save_config()
        except (ValueError, OSError):
            self.notify('請檢查日期、時段、票數、身分證及儲存位置，再啟動。', True)
            return
        self._stop.clear()
        self._received_done = False
        self._running, self._attempt, self._log = True, 0, ''
        self._match = {}
        self._phase = '準備啟動'
        self.navigate(2)
        self.notify('只查詢車次，不送出訂位。' if query_only else '自動訂位啟動，成功後停止；不付款。')
        self._thread = threading.Thread(target=self.worker,
                                        args=(config, self.path, query_only, self._stop, self._messages), daemon=False)
        self._thread.start()

    @Slot()
    def stop(self):
        self._stop.set()
        self.notify('正在停止，等待目前操作結束。已送出的訂位不會取消。')

    @Slot()
    def requestClose(self):
        if self._running:
            self._closing = True
            self.stop()
        else:
            self.closeReady.emit()

    @Slot()
    def poll(self):
        dirty = False
        while not self._messages.empty():
            kind, value = self._messages.get_nowait()
            dirty = True
            if kind == 'text':
                self._log = (self._log + value)[-60000:]
            elif kind == 'phase':
                self._phase = value
            elif kind == 'event':
                self._attempt = value.get('attempt', self._attempt)
                if value.get('event') == 'train_selected':
                    self._match = {key: value[key] for key in ('train_id', 'depart', 'arrive')}
                phases = {'homepage': '連線訂票網站', 'captcha_image': '取得驗證碼', 'ocr': '辨識驗證碼',
                          'query': '查詢車次', 'select_train': '選擇車次', 'submit_ticket': '送出訂位',
                          'parse_result': '確認訂位結果'}
                self._phase = phases.get(value.get('phase'), self._phase)
            elif kind == 'done':
                self._received_done = True
                self._phase = value
                self.notify(value)
                self.refresh()
        # Join before another task can start, including the short gap after its done event.
        if self._thread is not None and not self._thread.is_alive():
            dirty = True
            self._thread.join()
            self._thread = None
            self._running = False
            if not self._received_done:
                self._phase = '任務非預期結束'
                self.notify('任務未回傳完成狀態；請先在我的訂位確認結果，勿直接重送。', True)
            self.refresh()
            if self._closing:
                self.closeReady.emit()
        if dirty:
            self.changed.emit()
        countdown = ''
        if self._running and self._phase.startswith('等待啟動時間'):
            target = datetime.fromisoformat(self._form['start_at']).replace(tzinfo=TAIPEI)
            seconds = max(0, int((target - datetime.now(TAIPEI)).total_seconds()))
            countdown = f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'
        if countdown != self._countdown:
            self._countdown = countdown
            self.changed.emit()

    @Slot()
    def refresh(self):
        try:
            self._records = record_entries(self.path)
            self.changed.emit()
        except OSError:
            self.notify('紀錄無法讀取，請檢查資料位置。', True)

    @Slot(str)
    def archive(self, code):
        if self._running:
            return
        try:
            archive_booking(self.path, code, output=io.StringIO())
            self.refresh()
            self.notify('已移至歷史，官網訂位保留。可準備下一筆。')
        except (ValueError, OSError, RuntimeError):
            self.notify('未封存：紀錄已變更、仍在執行或無法寫入，請重新整理。', True)

    @Slot(str, str, str, bool)
    def resolve(self, fingerprint, outcome, code, confirmed):
        if self._running:
            return
        try:
            resolve_pending(self.path, outcome, fingerprint, confirmed=confirmed, code=code)
            self.refresh()
            self.notify('已保存核對結果並移至歷史，官網訂位未變更。')
        except (ValueError, OSError, RuntimeError):
            self.notify('未完成：請核對官網、填寫必要代碼並勾選確認；紀錄變更時請重新整理。', True)

    @Slot()
    def official(self):
        QDesktopServices.openUrl(QUrl('https://irs.thsrc.com.tw/IMINT/'))

    @Slot()
    def folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path.parent)))

    @Slot()
    def checkEnvironment(self):
        from thsr_ticket.remote.native_browser import browser_executable
        try:
            browser_executable('chrome')
            chrome = 'Chrome 可用'
        except RuntimeError:
            chrome = '未找到 Chrome，請先安裝'
        dependencies = all(importlib.util.find_spec(name) for name in ('playwright', 'ddddocr', 'onnxruntime'))
        self.notify(chrome + ('；自動化套件已安裝。' if dependencies else '；缺少自動化套件，請安裝桌面依賴。'))

"""Qt adapter: state and commands, with no network work on the UI thread."""
import io
import json
import queue
import threading
import os
import time
import math
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QApplication
from pydantic import ValidationError

from thsr_ticket.application import STATIONS, FIELDS, FieldError, form_config, protected_config_path, run_background
from thsr_ticket.automation import TAIPEI
from thsr_ticket.booking_records import (
    record_paths, archive_booking, resolve_pending, confirm_cancelled,
)
from thsr_ticket.config_store import (
    read_config_data, write_config_data, is_protected, ConfigVersionError, ConfigRestoreError,
)
from thsr_ticket.desktop.preferences import Preferences
from thsr_ticket.version import VERSION
from thsr_ticket.desktop.storage import StorageManager
from thsr_ticket.desktop.record_loader import RecordLoader
from thsr_ticket.desktop.tools import DesktopTools
from thsr_ticket.desktop.backup import BackupManager
from thsr_ticket.desktop.management import BookingManager
from thsr_ticket.desktop.retention import RetentionManager
from thsr_ticket.desktop.ocr_lab import OcrLab
from thsr_ticket.task_status import load_task, save_task, booking_guard, task_view
from thsr_ticket.record_search import RecordSearchIndex


def defaults():
    now = datetime.now(TAIPEI)
    return dict(start_at=now.strftime('%Y-%m-%d %H:%M:%S'), outbound_date=now.date().isoformat(),
                start_station='台北', dest_station='左營', earliest_departure='09:30', latest_departure='23:59',
                train_ids='', adult_tickets='1', child_tickets='0', disabled_tickets='0', elder_tickets='0',
                college_tickets='0', class_type='標準', personal_id='', phone_num='', interval_seconds='1',
                max_attempts='60', ocr_model='standard', network_failure_limit='3', max_network_delay_seconds='30')


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
    confirmRequested = Signal(str)
    storageRecoveryDetected = Signal()
    validationFailed = Signal(str)

    def __init__(self, data_dir, worker=run_background):
        super().__init__()
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / 'booking.local.json'
        self.preferences = Preferences(self.data_dir)
        previous = self.preferences.read().get('last_config')
        if isinstance(previous, str) and Path(previous).is_absolute():
            self.path = Path(previous)
        self.worker = worker
        self._form = defaults()
        self._saved_form = dict(self._form)
        self._protect_private = os.name == 'nt'
        self._saved_protection = self._protect_private
        self._records = []
        self._record_search = RecordSearchIndex(self._records)
        self._records_source = None
        self._record_loader = RecordLoader(self)
        self._record_loader.changed.connect(self.changed.emit)
        self._record_loader.loaded.connect(self.records_loaded)
        self._records_closing = False
        self._task_snapshot = {}
        self._guard = ''
        self._query_only = False
        self._stage = 'prepare'
        self._received_completion = False
        self._summary_warning = False
        self._status = '設定行程，開始下一段旅程。'
        self._phase = '尚未開始'
        self._attempt = 0
        self._running = False
        self._page = 0
        self._log = ''
        self._tools = DesktopTools(self.data_dir, self.preferences, self.tool_context, self)
        self._tools.notice.connect(self.notify)
        self._history = self._tools.historyDiagnostics
        self._history_closing = False
        self._storage = StorageManager(self)
        self._storage.changed.connect(self.changed.emit)
        self._storage.mutated.connect(self.refresh)
        self._storage.recoveryFound.connect(self.storageRecoveryDetected.emit)
        self._storage_closing = False
        self._backup = BackupManager(self.backup_context, self)
        self._backup.changed.connect(self.changed.emit)
        self._backup.notice.connect(self.notify)
        self.formChanged.connect(self._backup.invalidate_source)
        self._backup_closing = False
        self._management = BookingManager(self.backup_context, self)
        self._retention = RetentionManager(self.backup_context, self)
        self._ocr_lab = OcrLab(self.backup_context, self)
        self._extras_closing = False
        for service in (self._management, self._retention, self._ocr_lab):
            service.changed.connect(self.changed.emit)
            service.mutated.connect(self.refresh)
        self._error = False
        self._issues = {}
        self._match = {}
        self._countdown = ''
        self._retry_until = 0
        self._retry_reason = ''
        self._recovery = ''
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
        elif previous:
            self.notify('上次使用的設定已移動或不存在，請重新載入；不會自動建立另一份設定。', True)
        self.refresh()
        QTimer.singleShot(0, self.checkStorageRecovery)

    @Slot(str)
    def openNotification(self, target):
        if target in ('records', 'progress', 'settings'):
            self.navigate({'records': 3, 'progress': 2, 'settings': 4}[target])

    @Property(QObject, constant=True)
    def tools(self):
        return self._tools

    def tool_context(self):
        return {'config': self.path, 'task': self._task_snapshot.get('code', 'interrupted'),
                'query_only': self._query_only, 'guard': self._guard, 'phase': self._stage,
                'running': self.running}

    @Property(QObject, constant=True)
    def backup(self):
        return self._backup

    def backup_context(self):
        return {'config': self.path, 'running': self.running, 'dirty': self.dirty}

    @Slot(result=bool)
    def loadRestored(self):
        if self.running or self.dirty or not self._backup.restoredPath:
            return False
        if not self.load_path(self._backup.restoredPath):
            self._backup.report_error('backup_config_locked')
            return False
        return True

    @Property(QObject, constant=True)
    def storage(self):
        return self._storage

    @Property(QObject, constant=True)
    def management(self):
        return self._management

    @Property(QObject, constant=True)
    def retention(self):
        return self._retention

    @Property(QObject, constant=True)
    def ocrLab(self):
        return self._ocr_lab

    @Slot()
    def prepareStorage(self):
        if not self.running:
            self._storage.begin(self.path)

    @Slot()
    def checkStorageRecovery(self):
        if self.running:
            return
        _, runs = record_paths(self.path)
        root = runs.parent / (runs.name + '.operations')
        if root.exists() or root.is_symlink():
            self._storage.inspect(self.path)

    @Property('QVariantMap', notify=changed)
    def task(self):
        view = task_view(self._task_snapshot, self._guard, self._running, self._stop.is_set())
        view['can_book'] = view['can_book'] and not self.running
        view['step'] = {'prepare': 0, 'schedule': 1, 'homepage': 2, 'captcha_image': 2, 'ocr': 2,
                        'query': 2, 'select_train': 3, 'submit_ticket': 4, 'parse_result': 4}.get(self._stage, 0)
        if self._summary_warning:
            view['detail'] += ' 任務摘要無法保存；重新開啟時可能無法顯示本次狀態。'
        return view

    def persist_task(self, code):
        self._task_snapshot = {'code': code, 'query_only': self._query_only}
        try:
            save_task(self.path, code, self._query_only)
            self._summary_warning = False
        except (ValueError, OSError):
            self._summary_warning = True

    @Slot()
    def taskAction(self):
        action = self.task['action']
        if action == 'official':
            self.official()
        else:
            self.navigate({'records': 3, 'settings': 4, 'progress': 2, 'edit': 1}[action])

    def record_action_finished(self):
        self._query_only = False
        self.persist_task('success')
        self._recovery = ''
        self.refresh()
        self._phase = self.task['title']

    @Property(bool, notify=formChanged)
    def dirty(self):
        return self._form != self._saved_form or self._protect_private != self._saved_protection

    @Property(bool, notify=formChanged)
    def protectPrivate(self):
        return self._protect_private

    @Property(bool, constant=True)
    def protectionAvailable(self):
        return os.name == 'nt'

    @Slot(bool)
    def setProtection(self, enabled):
        if not self._running and (not enabled or self.protectionAvailable):
            self._protect_private = enabled
            self.formChanged.emit()

    @Property(str, notify=changed)
    def recovery(self):
        return self._recovery

    @Property(str, constant=True)
    def version(self):
        return VERSION

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

    @Property(str, notify=changed)
    def retryReason(self):
        return self._retry_reason if self._running and self._stage == 'retry_wait' else ''

    @Property('QStringList', constant=True)
    def stations(self):
        return STATIONS

    @Property('QVariantList', notify=changed)
    def records(self):
        return self._records

    @Property(int, notify=changed)
    def recordCount(self):
        return len(self._records)

    @Property(int, notify=changed)
    def currentRecordCount(self):
        return self.search_index().current_count

    def search_index(self):
        if self._record_search.source is not self._records:
            self._record_search = RecordSearchIndex(self._records)
        return self._record_search

    @Slot(bool, str, str, int, int, result='QVariantMap')
    def recordPageData(self, history, search, date, status, page):
        return self.search_index().page(history, search, date, status, page)

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
        return (self._running or self._storage.busy or self._backup.busy or self._management.busy
                or self._retention.busy or self._ocr_lab.busy)

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
        if not self.running and key in self._form:
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
        if not self.running:
            a, b = self._form['start_station'], self._form['dest_station']
            self._form.update(start_station=b, dest_station=a)
            self.formChanged.emit()

    def load_path(self, path):
        if self.running:
            return False
        try:
            raw = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            new = form_values(read_config_data(path))
            # Keep the original location: its state/runs guard must follow the setting.
            self.path = Path(path).resolve()
            if self._history.config != self.path:
                self._history.reset(self.path)
            self._form = new
            self._saved_form = dict(new)
            self._protect_private = is_protected(raw)
            self._saved_protection = self._protect_private
            self._issues = {}
            self._summary_warning = False
            self._log, self._attempt, self._match = '', 0, {}
            self._recovery = ''
            self.resetSecrets.emit()
            self.formChanged.emit()
            self.refresh()
            self._phase = self.task['title']
            self.notify('已載入設定，請核對日期與時間。')
            self.remember()
            QTimer.singleShot(0, self.checkStorageRecovery)
            return True
        except (ConfigVersionError, ConfigRestoreError) as exc:
            self.notify(str(exc), True)
            return False
        except (ValueError, OSError, TypeError):
            self.notify('無法載入；請選擇有效的訂票設定 JSON。', True)
            return False

    @Slot()
    def load(self):
        if self.running:
            return
        if self.dirty:
            self.confirmRequested.emit('load')
            return
        self.choose_load()

    def choose_load(self):
        path, _ = QFileDialog.getOpenFileName(None, '載入設定', str(self.path.parent), 'JSON (*.json)')
        if path:
            self.load_path(path)

    def remember(self):
        try:
            self.preferences.remember(self.path)
        except OSError:
            self.notify('設定可使用，但無法記住檔案位置；下次需手動載入。', True)

    def save_config(self):
        self._issues = {}
        try:
            config = form_config({key: value.strip() for key, value in self._form.items()})
        except FieldError as exc:
            self._issues[exc.field] = str(exc)
            self.changed.emit()
            self.validationFailed.emit(exc.field)
            raise
        except ValidationError as exc:
            for error in exc.errors():
                key = next((str(part) for part in reversed(error['loc']) if str(part) in self._form), '__root__')
                details = {'interval_seconds': '請輸入大於 0 的秒數。', 'max_attempts': '請輸入 1～10000。',
                           'personal_id': '請檢查身分證或證件號碼格式。', 'outbound_date': '請輸入有效搭車日期。',
                           'earliest_departure': '請使用 00:00～23:59。', 'latest_departure': '請使用 00:00～23:59。',
                           '__root__': '請檢查起訖站不同、票數合計 1～10，以及日期與時間先後順序。'}
                self._issues[key] = details.get(key, '請檢查格式與範圍。')
            self.changed.emit()
            self.validationFailed.emit(next((key for key in self._issues if key != '__root__'), '__root__'))
            raise
        if protected_config_path(self.path):
            raise ValueError('範本不能直接儲存，請先在設定頁另存個人設定。')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_config_data(self.path, json.loads(config.json()), protect=self._protect_private)
        self._saved_form = dict(self._form)
        self._saved_protection = self._protect_private
        self.formChanged.emit()
        self.remember()
        return config

    @Slot()
    def save(self):
        if self.running:
            return
        try:
            self.save_config()
            self.notify('設定已儲存。')
        except (ConfigVersionError, ConfigRestoreError) as exc:
            self.notify(str(exc), True)
        except (ValueError, OSError):
            self.notify('儲存失敗：請檢查日期、時段、票數、身分證與儲存位置。', True)

    @Slot()
    def saveAs(self):
        if self.running:
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
        if self.running:
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
        self._query_only = query_only
        self._stage = 'prepare'
        self.persist_task('running')
        self._recovery = ''
        self._received_done = False
        self._received_completion = False
        self._tools.begin_task()
        self._running, self._attempt, self._log = True, 0, ''
        self._match = {}
        self._phase = '準備啟動'
        self.navigate(2)
        self.notify('只查詢車次，不送出訂位。' if query_only else '自動訂位啟動，成功後停止；不付款。')
        self._thread = threading.Thread(target=self.worker,
                                        args=(config, self.path, query_only, self._stop, self._messages), daemon=False)
        try:
            self._thread.start()
        except RuntimeError:
            self._thread = None
            self._running = False
            self.persist_task('operation_failed')
            self._phase = '任務無法啟動'
            self.notify('無法啟動背景工作，請關閉並重新開啟 App。', True)
            self._tools.notify_task_finished()

    @Slot()
    def stop(self):
        self._stop.set()
        self.notify('正在停止，等待目前操作結束。已送出的訂位不會取消。')

    @Slot()
    def requestClose(self):
        if self._management.busy or self._retention.busy or self._ocr_lab.busy:
            self._extras_closing = True
            self._management.stop()
            self._retention.cancel()
            self._ocr_lab.cancel()
            return
        if self._backup.busy:
            self._backup_closing = True
            self._backup.cancel()
            return
        if self._history.busy and not self._running and not self._storage.busy:
            self._history_closing = True
            self._history.cancel()
            return
        if self._record_loader.busy and not self._running and not self._storage.busy:
            self._records_closing = True
            self._record_loader.cancel()
            return
        if self._storage.busy:
            self._storage_closing = True
            self._storage.cancel()
            return
        if self.running:
            self._closing = True
            self.stop()
        elif self.dirty:
            self.confirmRequested.emit('close')
        else:
            self.closeReady.emit()

    @Slot(str, str)
    def confirmAction(self, action, decision):
        if self.running or action not in ('close', 'load') or decision not in ('save', 'discard'):
            return
        if decision == 'save':
            try:
                self.save_config()
            except (ValueError, OSError):
                self.notify('尚未儲存，請修正設定後再繼續。', True)
                return
        if action == 'close':
            self.closeReady.emit()
        else:
            self.choose_load()

    @Slot()
    def recover(self):
        if self._recovery == 'official':
            self.official()
            return
        self.navigate({'records': 3, 'settings': 4, 'edit': 1}.get(self._recovery, 1))

    @Slot()
    def poll(self):
        self._management.poll()
        self._retention.poll()
        self._ocr_lab.poll()
        if self._extras_closing and not (self._management.busy or self._retention.busy or self._ocr_lab.busy):
            self._extras_closing = False
            self.requestClose()
        self._backup.poll()
        if self._backup_closing and not self._backup.busy:
            self._backup_closing = False
            self.requestClose()
        self._tools.poll()
        self._history.poll()
        if self._history_closing and not self._history.busy:
            self._history_closing = False
            self.requestClose()
        self._record_loader.poll()
        if self._records_closing and not self._record_loader.busy:
            self._records_closing = False
            self.requestClose()
        if self._storage_closing and not self._storage.busy:
            self._storage_closing = False
            self.requestClose()
        dirty = False
        while not self._messages.empty():
            kind, value = self._messages.get_nowait()
            dirty = True
            if kind == 'text':
                self._log = (self._log + value)[-60000:]
            elif kind == 'phase':
                self._phase = value
                if value.startswith('等待啟動時間'):
                    self._stage = 'schedule'
            elif kind == 'event':
                self._tools.record_event(value)
                if value.get('phase'):
                    self._stage = value['phase']
                if value.get('event') == 'retry_scheduled':
                    self._retry_until = time.monotonic() + value['delay_seconds']
                    self._retry_reason = {'network_retry': '連線暫時失敗', 'captcha_rejected': '驗證碼未通過',
                                          'ocr_no_candidate': '辨識結果不可靠',
                                          'no_matching_train': '沒有符合條件的車次'}.get(value.get('outcome'), '準備重查')
                    self._phase = '等待下一次查詢'
                self._attempt = value.get('attempt', self._attempt)
                if value.get('event') == 'train_selected':
                    self._match = {key: value[key] for key in ('train_id', 'depart', 'arrive')}
                phases = {'homepage': '連線訂票網站', 'captcha_image': '取得驗證碼', 'ocr': '辨識驗證碼',
                          'query': '查詢車次', 'select_train': '選擇車次', 'submit_ticket': '送出訂位',
                          'parse_result': '確認訂位結果'}
                self._phase = phases.get(value.get('phase'), self._phase)
            elif kind == 'done':
                self._received_done = True
                if not self._received_completion:
                    self.persist_task('stopped' if self._stop.is_set() else 'success')
                self._phase = value
                self.notify(value, self._error)
                self.refresh()
            elif kind == 'completion':
                self._received_completion = True
                self.persist_task(value['code'])
                self._error = value['code'] not in ('success', 'stopped')
                self._recovery = value['action']
        # Join before another task can start, including the short gap after its done event.
        if self._thread is not None and not self._thread.is_alive():
            dirty = True
            self._thread.join()
            self._thread = None
            self._running = False
            if not self._received_done:
                self.persist_task('interrupted')
                self._phase = '任務非預期結束'
                self.notify('任務未回傳完成狀態；請先在我的訂位確認結果，勿直接重送。', True)
            self.refresh()
            self._tools.notify_task_finished()
            if self._closing:
                self._closing = False
                self.requestClose()
        if dirty:
            self.changed.emit()
        countdown = ''
        if self._running and self._stage == 'retry_wait':
            seconds = max(0, math.ceil(self._retry_until - time.monotonic()))
            countdown = f'{seconds} 秒後重查'
        if self._running and self._phase.startswith('等待啟動時間'):
            target = datetime.fromisoformat(self._form['start_at']).replace(tzinfo=TAIPEI)
            seconds = max(0, int((target - datetime.now(TAIPEI)).total_seconds()))
            countdown = f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'
        if countdown != self._countdown:
            self._countdown = countdown
            self.changed.emit()

    @Property(bool, notify=changed)
    def recordsLoading(self):
        return self._record_loader.busy

    @Property(str, notify=changed)
    def recordsSummary(self):
        report = self._record_loader.report
        if not report:
            return ''
        return f"已讀 {report['accepted']} 個來源，略過 {report['skipped']}，讀取失敗 {report['failed']}。"

    @Property('QVariantList', notify=changed)
    def recordsReasons(self):
        return self._record_loader.report.get('reasons', [])

    def records_loaded(self, config, entries, error):
        if config != self.path:
            return
        self._records = entries
        prepared = self._record_loader.search_index
        self._record_search = (prepared if prepared is not None and prepared.source is entries
                               else RecordSearchIndex(entries))
        if error:
            self.notify(error['title'] + '；' + error['guidance'], True)
        self.changed.emit()

    @Slot()
    def refresh(self):
        self._guard = booking_guard(self.path)
        if not self._running and not self._summary_warning:
            self._task_snapshot = load_task(self.path)
        if self._records_source != self.path:
            self._records = []
            self._record_loader.report = {}
            self._records_source = self.path
        self._record_loader.request(self.path)
        self.changed.emit()

    @Slot(str)
    def archive(self, code):
        if self.running:
            return
        try:
            archive_booking(self.path, code, output=io.StringIO())
            self.record_action_finished()
            self.notify('已移至歷史，官網訂位保留。可準備下一筆。')
        except (ValueError, OSError, RuntimeError):
            self.notify('未封存：紀錄已變更、仍在執行或無法寫入，請重新整理。', True)

    @Slot(str, str, str, bool)
    def resolve(self, fingerprint, outcome, code, confirmed):
        if self.running:
            return
        try:
            resolve_pending(self.path, outcome, fingerprint, confirmed=confirmed, code=code)
            self.record_action_finished()
            self.notify('已保存核對結果並移至歷史，官網訂位未變更。')
        except (ValueError, OSError, RuntimeError):
            self.notify('未完成：請核對官網、填寫必要代碼並勾選確認；紀錄變更時請重新整理。', True)

    @Slot()
    def official(self):
        QDesktopServices.openUrl(QUrl('https://irs.thsrc.com.tw/IMINT/'))

    @Slot(str, result=bool)
    def openCancellation(self, code):
        if self._running or not any(item.get('code') == code and item.get('current')
                                    and item.get('status') == 'booked' for item in self._records):
            return False
        opened = QDesktopServices.openUrl(QUrl(
            'https://irs.thsrc.com.tw/IMINT/?wicket:bookmarkablePage=:tw.com.mitac.webapp.thsr.viewer.History'))
        self.notify('請在官網查詢該筆訂位，核對行程後操作取消；完成後回到此視窗確認。' if opened
                    else '無法開啟瀏覽器，請手動進入高鐵官網「管理訂位」。', not opened)
        return opened

    @Slot(str, str, bool)
    def confirmCancellation(self, code, fingerprint, confirmed):
        if self.running:
            return
        try:
            confirm_cancelled(self.path, code, fingerprint, confirmed)
            self.record_action_finished()
            self.notify('已依你的官網確認結果標記取消並封存，可準備下一筆訂位。')
        except (ValueError, OSError, RuntimeError):
            self.notify('未變更紀錄：請確認官網取消結果，並重新整理本機紀錄。', True)

    @Slot(str)
    def copyCode(self, code):
        if code and any(entry.get('code') == code for entry in self._records):
            QApplication.clipboard().setText(code)
            self.notify('訂位代碼已複製。')

    @Slot()
    def folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path.parent)))

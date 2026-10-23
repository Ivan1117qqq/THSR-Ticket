"""Desktop diagnostics, notification preferences and environment tools; no booking decisions."""
import importlib.util
import json
import queue
import threading
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from thsr_ticket.desktop.history import HistoryDiagnostics
from thsr_ticket.desktop.notifications import task_notification
from thsr_ticket.desktop.updates import check_release, RELEASES
from thsr_ticket.diagnostics import safe_event, snapshot
from thsr_ticket.version import VERSION


class DesktopTools(QObject):
    changed = Signal()
    notice = Signal(str, bool)
    desktopNotification = Signal(str, str, str)
    notificationsChanged = Signal(bool)

    def __init__(self, directory, preferences, context, parent=None):
        super().__init__(parent)
        self.data_dir = Path(directory)
        self.preferences = preferences
        self.context = context
        self._notifications_enabled = preferences.read().get('desktop_notifications') is True
        self._notification_available = False
        self._notification_emitted = False
        self._diagnostic_events = deque(maxlen=200)
        self._diagnostic_preview = ''
        self._diagnostic_scope = 'session'
        self._history = HistoryDiagnostics(self)
        self._history.changed.connect(self.changed.emit)
        self._update_checking = False
        self._update_available = False
        self._update_message = '手動檢查正式版本，不會自動下載或覆蓋程式。'
        self._messages = queue.Queue()

    def notify(self, message, error=False):
        self.notice.emit(message, error)
        self.changed.emit()

    def begin_task(self):
        self._notification_emitted = False

    def record_event(self, value):
        clean = safe_event(value)
        if clean:
            self._diagnostic_events.append(clean)

    @Slot()
    def testNotification(self):
        if not self._notifications_enabled:
            self.notify('請先啟用任務通知。')
            return
        if not self._notification_available:
            self.notify('目前系統不支援桌面通知。', True)
            return
        self.desktopNotification.emit('Travel Desk 測試通知', '通知功能已送出；點擊可回到設定頁。', 'settings')
        self.notify('已送出測試通知；未看到時請檢查 Windows 通知與勿擾設定。')

    def poll(self):
        while not self._messages.empty():
            result = self._messages.get_nowait()
            self._update_checking = False
            self._update_message = result['message']
            self._update_available = result['available']
            self.changed.emit()

    @Property(str, notify=changed)
    def diagnosticPreview(self):
        return self._diagnostic_preview

    @Property(str, notify=changed)
    def diagnosticDescription(self):
        return ('歷史任務讀取時的快照，最多 200 筆過濾事件；版本以該次保存內容為準，未記錄者標示 unknown。'
                if self._diagnostic_scope == 'history' else
                '本次開啟 App 最近 200 筆過濾事件與狀態；不含個資、訂位代碼或完整日誌。')

    @Property(QObject, constant=True)
    def historyDiagnostics(self):
        return self._history

    @Slot()
    def prepareHistory(self):
        self._history.begin(self.context()['config'])

    @Slot(result=bool)
    def prepareHistoricalDiagnostics(self):
        if self._history.busy or not self._history.preview or self._history.config != self.context()['config']:
            return False
        self._diagnostic_preview = self._history.preview
        self._diagnostic_scope = 'history'
        self.changed.emit()
        return True

    @Property(bool, notify=changed)
    def notificationsEnabled(self):
        return self._notifications_enabled

    @Property(bool, notify=changed)
    def notificationsAvailable(self):
        return self._notification_available

    def set_notification_support(self, available):
        self._notification_available = bool(available)
        self.changed.emit()

    @Slot(bool)
    def setNotifications(self, enabled):
        try:
            self.preferences.notifications(enabled)
        except OSError:
            self.notify('通知設定無法保存，請確認 App 資料夾權限。', True)
            self.changed.emit()
            return
        self._notifications_enabled = enabled
        self.notificationsChanged.emit(enabled)
        self.changed.emit()

    def notify_task_finished(self):
        if self._notification_emitted:
            return
        self._notification_emitted = True
        if not self._notifications_enabled:
            return
        context = self.context()
        item = task_notification(context['task'], context['query_only'], context['guard'], context['phase'])
        if item:
            self.desktopNotification.emit(item['title'], item['body'], item['target'])

    @Slot()
    def prepareDiagnostics(self):
        self._diagnostic_scope = 'session'
        context = self.context()
        self._diagnostic_preview = json.dumps(snapshot(
            self._diagnostic_events, context['task'], context['guard'], context['running']),
            ensure_ascii=False, indent=2)
        self.changed.emit()

    @Slot()
    def exportDiagnostics(self):
        if not self._diagnostic_preview:
            return
        target, _ = QFileDialog.getSaveFileName(
            None, '匯出診斷資料', str(self.data_dir / 'travel-desk.diagnostics.json'), 'JSON (*.json)')
        if not target:
            return
        if not target.endswith('.diagnostics.json'):
            self.notify('請使用 .diagnostics.json 副檔名，以免與訂票設定混淆。', True)
            return
        try:
            with Path(target).open('x', encoding='utf-8') as handle:
                handle.write(self._diagnostic_preview + '\n')
            self.notify('診斷資料已匯出；未傳送至網路。')
        except FileExistsError:
            self.notify('檔案已存在，請選擇新的檔名。', True)
        except OSError:
            self.notify('無法匯出診斷資料，請確認目的資料夾可寫入。', True)

    @Property(bool, notify=changed)
    def updateChecking(self):
        return self._update_checking

    @Property(bool, notify=changed)
    def updateAvailable(self):
        return self._update_available

    @Property(str, notify=changed)
    def updateMessage(self):
        return self._update_message

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

    @Slot()
    def checkUpdates(self):
        if self.context()['running'] or self._update_checking:
            return
        self._update_checking = True
        self._update_message = '正在檢查 GitHub 正式版本…'
        self.changed.emit()

        def check():
            try:
                result = check_release(VERSION)
            except Exception:
                result = {'message': '無法檢查更新，現有版本仍可使用。稍後可再試。', 'available': False}
            self._messages.put(result)
        try:
            threading.Thread(target=check, daemon=True).start()
        except RuntimeError:
            self._update_checking = False
            self._update_message = '無法啟動更新檢查，請稍後再試。'
            self.changed.emit()

    @Slot()
    def releasePage(self):
        QDesktopServices.openUrl(QUrl(RELEASES))

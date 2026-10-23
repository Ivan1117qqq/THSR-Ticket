"""One cooperative local worker with main-thread delivery and explicit lifetime."""
import queue
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot
from thsr_ticket.scan_report import ScanCancelled
from thsr_ticket.storage_errors import error_info


class LocalJob(QObject):
    changed = Signal()
    notice = Signal(str, bool)
    mutated = Signal()

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self._thread = None
        self._cancel = threading.Event()
        self._queue = queue.Queue()
        self._busy = self._cancellable = False
        self._message = ''
        self._result = {}

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=changed)
    def cancellable(self):
        return self._busy and self._cancellable

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property('QVariantMap', notify=changed)
    def result(self):
        return self._result

    @Slot()
    def cancel(self):
        if self._cancellable:
            self._cancel.set()

    def launch(self, action, work, cancellable=True):
        if self._busy or self.context()['running']:
            return False
        self._busy, self._cancellable = True, cancellable
        self._cancel.clear()
        self._result = {}
        self._message = '正在處理…'

        def run():
            try:
                self._queue.put((action, work(), ''))
            except ScanCancelled:
                self._queue.put(('cancelled', {}, ''))
            except Exception as exc:
                self._queue.put(('error', {}, self.error_message(exc)))

        self._thread = threading.Thread(target=run, daemon=False)
        try:
            self._thread.start()
        except RuntimeError:
            self._thread = None
            self._busy = self._cancellable = False
            self._message = '無法啟動背景工作，請重新開啟 App。'
        self.changed.emit()
        return self._busy

    def completed(self, action, value):
        self._result = value
        self._message = '處理完成。'

    def error_message(self, error):
        info = error_info(error)
        return info['title'] + '。' + info['guidance']

    def poll(self):
        if self._thread is None or self._thread.is_alive():
            return
        self._thread.join()
        self._thread = None
        action, value, error = self._queue.get_nowait()
        self._busy = self._cancellable = False
        if error or action == 'cancelled':
            self._message = error or '已取消，未執行後續操作。'
        else:
            self.completed(action, value)
        self.changed.emit()

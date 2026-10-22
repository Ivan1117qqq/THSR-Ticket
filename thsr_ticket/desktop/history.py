"""Background, cancellable history diagnostics; only sanitized snapshots reach Qt."""
import json
import queue
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot

from thsr_ticket.history_diagnostics import scan_history
from thsr_ticket.scan_report import ScanCancelled
from thsr_ticket.storage_errors import error_info, StorageError


class HistoryDiagnostics(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = None
        self._rows, self._snapshots = [], {}
        self._selected = {}
        self._preview = ''
        self._message = ''
        self._busy = False
        self._generation = 0
        self._cancel = threading.Event()
        self._thread = None
        self._pending = None
        self._queue = queue.Queue()

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property('QVariantList', notify=changed)
    def rows(self):
        return self._rows

    @Property('QVariantMap', notify=changed)
    def selected(self):
        return self._selected

    @Property(str, notify=changed)
    def preview(self):
        return self._preview

    @Property(str, notify=changed)
    def message(self):
        return self._message

    def begin(self, config):
        self._generation += 1
        self.config = config
        self._pending = (self._generation, config)
        self._cancel.set()
        self._rows, self._snapshots, self._selected, self._preview = [], {}, {}, ''
        self._busy, self._message = True, '正在讀取歷史任務…'
        if self._thread is None:
            self._launch()
        self.changed.emit()

    def reset(self, config):
        self.cancel()
        self.config = config
        self._rows, self._snapshots, self._selected, self._preview = [], {}, {}, ''
        self._message = '請重新讀取目前設定的歷史任務。'
        self.changed.emit()

    @Slot()
    def cancel(self):
        self._generation += 1
        self._pending = None
        self._cancel.set()
        self._message = '已要求取消讀取。'
        self.changed.emit()

    @Slot(str)
    def select(self, identifier):
        if self._busy or identifier not in self._snapshots:
            return
        self._selected = next(row for row in self._rows if row['id'] == identifier)
        self._preview = json.dumps(self._snapshots[identifier], ensure_ascii=False, indent=2)
        self.changed.emit()

    def _launch(self):
        generation, config = self._pending
        self._pending = None
        self._cancel = threading.Event()
        cancel = self._cancel

        def work():
            try:
                self._queue.put((generation, scan_history(config, cancel), {}))
            except ScanCancelled:
                self._queue.put((generation, None, {}))
            except Exception as error:
                self._queue.put((generation, None, error_info(error)))

        self._thread = threading.Thread(target=work, daemon=False)
        try:
            self._thread.start()
        except RuntimeError:
            self._thread = None
            self._busy = False
            self._message = error_info(StorageError('worker_start_failed'))['guidance']

    def poll(self):
        if self._thread is None or self._thread.is_alive():
            return
        self._thread.join()
        self._thread = None
        result = None
        while not self._queue.empty():
            value = self._queue.get_nowait()
            if value[0] == self._generation:
                result = value
        if self._pending is not None:
            self._launch()
        else:
            self._busy = False
            if result is not None:
                _, data, error = result
                if error:
                    self._message = error['title'] + '；' + error['guidance']
                elif data is not None:
                    self._rows, self._snapshots, report = data
                    self._message = (f'已讀 {report["accepted"]} 次任務；略過 {report["skipped"]}，'
                                     f'讀取失敗 {report["failed"]}。另有 {report["not_loaded"]} 次超出最近 200 次範圍。')
        self.changed.emit()

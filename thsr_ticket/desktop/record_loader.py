"""Coalesced background booking reads; obsolete snapshots never reach the UI."""
import queue
import threading

from PySide6.QtCore import QObject, Signal

from thsr_ticket.booking_records import record_entries
from thsr_ticket.scan_report import ScanReport, ScanCancelled
from thsr_ticket.storage_errors import error_info, StorageError
from thsr_ticket.record_search import RecordSearchIndex


class RecordLoader(QObject):
    changed = Signal()
    loaded = Signal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False
        self.report = {}
        self.error = {}
        self.search_index = None
        self._generation = 0
        self._pending = None
        self._thread = None
        self._cancel = threading.Event()
        self._queue = queue.Queue()

    def request(self, config):
        self._generation += 1
        self._pending = (self._generation, config)
        self._cancel.set()
        self.busy = True
        if self._thread is None:
            self._launch()
        self.changed.emit()

    def cancel(self):
        self._generation += 1
        self._pending = None
        self._cancel.set()

    def _launch(self):
        generation, config = self._pending
        self._pending = None
        self._cancel = threading.Event()
        cancel = self._cancel

        def work():
            report = ScanReport()
            try:
                entries = record_entries(config, cancel=cancel, report=report)
                index = RecordSearchIndex(entries, cancel)
                self._queue.put((generation, config, entries, report.snapshot(), {}, index))
            except ScanCancelled:
                self._queue.put((generation, config, [], {}, {}, None))
            except Exception as error:
                self._queue.put((generation, config, [], report.snapshot(), error_info(error), None))

        self._thread = threading.Thread(target=work, daemon=False)
        try:
            self._thread.start()
        except RuntimeError:
            self._thread = None
            self.busy = False
            self.error = error_info(StorageError('worker_start_failed'))
            self.loaded.emit(config, [], self.error)
            self.changed.emit()

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
            self.busy = False
            if result is not None:
                _, config, entries, self.report, self.error, self.search_index = result
                self.loaded.emit(config, entries, self.error)
        self.changed.emit()

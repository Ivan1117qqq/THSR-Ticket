"""Background record management; workers return data, never touch Qt properties."""
import queue
import threading
from datetime import date

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from thsr_ticket.booking_records import record_paths
from thsr_ticket.record_storage import inventory, backup_batches, move_history, restore_history, ScanCancelled


class StorageManager(QObject):
    changed = Signal()
    mutated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = None
        self.items = []
        self.selected = set()
        self.batches = []
        self._busy = False
        self._scanning = False
        self._message = ''
        self._after = ''
        self._before = ''
        self._cancel = threading.Event()
        self._queue = queue.Queue()
        self._thread = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._timer.start(80)

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=changed)
    def scanning(self):
        return self._scanning

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property('QVariantList', notify=changed)
    def rows(self):
        return [{**item, 'selected': item['id'] in self.selected} for item in self.items
                if (not self._after or item['date'][:10] >= self._after)
                and (not self._before or item['date'][:10] <= self._before)]

    @Property('QVariantList', notify=changed)
    def backups(self):
        return self.batches

    @Property(int, notify=changed)
    def selectedCount(self):
        return len(self.selected)

    @Property(str, notify=changed)
    def selectionSummary(self):
        size = sum(item['bytes'] for item in self.items if item['id'] in self.selected)
        return f'已選 {len(self.selected)} 筆 · {size:,} bytes'

    @Slot(str, str)
    def filterDates(self, after, before):
        if self.busy:
            return
        try:
            for value in (after, before):
                if value and date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            if after and before and after > before:
                raise ValueError()
        except ValueError:
            self._message = '請填寫有效的 YYYY-MM-DD 日期，起日不可晚於迄日。'
            self.changed.emit()
            return
        self._after, self._before = after, before
        self.selected.clear()  # Hidden selections must never be moved accidentally.
        self._message = '篩選已套用，請重新勾選紀錄。'
        self.changed.emit()

    @Slot(str, bool)
    def select(self, identifier, checked):
        if self.busy or identifier not in {row['id'] for row in self.rows}:
            return
        if checked:
            self.selected.add(identifier)
        else:
            self.selected.discard(identifier)
        self.changed.emit()

    @Slot(bool)
    def selectVisible(self, checked):
        if not self.busy:
            self.selected = {row['id'] for row in self.rows} if checked else set()
            self.changed.emit()

    def begin(self, config):
        if self.busy:
            return
        self.config = config
        self.items, self.batches = [], []
        self.selected.clear()
        self._launch('scan', None)

    @Slot()
    def cancel(self):
        if self.scanning:
            self._cancel.set()
            self._message = '正在取消掃描…'
            self.changed.emit()

    @Slot()
    def moveSelected(self):
        if not self.busy and self.selected:
            self._launch('move', [item for item in self.items if item['id'] in self.selected])

    @Slot(str)
    def restoreBatch(self, identifier):
        if not self.busy and identifier in {item['id'] for item in self.batches}:
            self._launch('restore', identifier)

    def _launch(self, action, payload):
        self._busy = True
        self._scanning = action == 'scan'
        self._cancel.clear()
        self._message = '正在掃描…' if self._scanning else '正在處理，請等待完成…'
        config = self.config

        def work():
            try:
                if action == 'scan':
                    items = inventory(config, self._cancel,
                                      lambda count: self._queue.put(('progress', count)))
                    batches = backup_batches(config, self._cancel)
                    blocked = record_paths(config)[0].exists()
                    self._queue.put(('scan', (items, batches, blocked)))
                elif action == 'move':
                    move_history(config, payload)
                    self._queue.put(('mutated', None))
                else:
                    _, runs = record_paths(config)
                    root = runs.parent / (runs.name + '.history-backups')
                    restore_history(config, root / payload)
                    self._queue.put(('mutated', None))
            except ScanCancelled:
                self._queue.put(('cancelled', None))
            except Exception:
                self._queue.put(('error', None))

        self._thread = threading.Thread(target=work, daemon=False)
        try:
            self._thread.start()
        except RuntimeError:
            self._busy = self._scanning = False
            self._message = '無法啟動背景工作，請重新開啟程式。'
        self.changed.emit()

    @Slot()
    def poll(self):
        while not self._queue.empty():
            kind, value = self._queue.get_nowait()
            if kind == 'progress':
                if not self._cancel.is_set():
                    self._message = f'已檢查 {value} 個目錄…'
            else:
                self._busy = self._scanning = False
                if kind == 'scan' and not self._cancel.is_set():
                    self.items, self.batches, blocked = value
                    self._message = ('目前有訂位狀態，請先核對並封存。仍可還原備份。' if blocked
                                     else f'找到 {len(self.items)} 筆可整理紀錄、{len(self.batches)} 個備份批次。')
                elif kind == 'mutated':
                    self.items, self.batches = [], []
                    self.selected.clear()
                    self._message = '處理完成，請重新掃描查看最新紀錄。官網訂位不變。'
                    self.mutated.emit()
                else:
                    self.items, self.batches = [], []
                    self.selected.clear()
                    self._message = ('掃描已取消，沒有移動任何紀錄。' if kind in ('scan', 'cancelled')
                                     else '無法完成，請保留原始紀錄與備份，重新掃描後再試。')
            self.changed.emit()

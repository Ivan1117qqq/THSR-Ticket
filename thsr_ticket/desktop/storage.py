"""Background record management; workers return data, never touch Qt properties."""
import queue
import threading
from datetime import date

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from thsr_ticket.booking_records import record_paths
from thsr_ticket.record_storage import inventory, backup_batches, move_history, restore_history, ScanCancelled
from thsr_ticket.storage_errors import error_info, StorageError
from thsr_ticket.storage_journal import pending_operations, recover_operation


class StorageManager(QObject):
    changed = Signal()
    mutated = Signal()
    recoveryFound = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = None
        self.items = []
        self.selected = set()
        self.batches = []
        self._recoveries = []
        self._error = {}
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

    @Property('QVariantMap', notify=changed)
    def error(self):
        return self._error

    @Property('QVariantList', notify=changed)
    def recoveries(self):
        return self._recoveries

    @Property(bool, notify=changed)
    def hasRecovery(self):
        return bool(self._recoveries)

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

    def inspect(self, config):
        if not self.busy:
            self.config = config
            self.items, self.batches, self._recoveries = [], [], []
            self.selected.clear()
            self._launch('inspect', None)

    @Slot()
    def cancel(self):
        if self.scanning:
            self._cancel.set()
            self._message = '正在取消掃描…'
            self.changed.emit()

    @Slot()
    def moveSelected(self):
        if not self.busy and self.selected and not self.hasRecovery:
            self._launch('move', [item for item in self.items if item['id'] in self.selected])

    @Slot(str)
    def restoreBatch(self, identifier):
        if not self.busy and not self.hasRecovery and identifier in {item['id'] for item in self.batches}:
            self._launch('restore', identifier)

    @Slot(str)
    def recover(self, identifier):
        if not self.busy and any(item['id'] == identifier and item['recoverable'] for item in self._recoveries):
            self._launch('recover', identifier)

    def _launch(self, action, payload):
        self._busy = True
        self._scanning = action in ('scan', 'inspect')
        self._error = {}
        self._cancel.clear()
        self._message = '正在掃描…' if self._scanning else '正在處理，請等待完成…'
        config = self.config

        def work():
            try:
                if action == 'inspect':
                    operations = pending_operations(config, self._cancel)
                    if self._cancel.is_set():
                        raise ScanCancelled()
                    self._queue.put(('inspect', operations))
                elif action == 'scan':
                    operations = pending_operations(config, self._cancel)
                    items = inventory(config, self._cancel,
                                      lambda count: self._queue.put(('progress', count)))
                    batches = backup_batches(config, self._cancel)
                    blocked = record_paths(config)[0].exists()
                    self._queue.put(('scan', (items, batches, blocked, operations)))
                elif action == 'move':
                    move_history(config, payload)
                    self._queue.put(('mutated', pending_operations(config)))
                elif action == 'restore':
                    _, runs = record_paths(config)
                    root = runs.parent / (runs.name + '.history-backups')
                    restore_history(config, root / payload)
                    self._queue.put(('mutated', pending_operations(config)))
                else:
                    recover_operation(config, payload)
                    self._queue.put(('mutated', pending_operations(config)))
            except ScanCancelled:
                self._queue.put(('cancelled', None))
            except Exception as error:
                try:
                    operations = pending_operations(config)
                except Exception:
                    operations = None
                self._queue.put(('error', (error_info(error), operations)))

        self._thread = threading.Thread(target=work, daemon=False)
        try:
            self._thread.start()
        except RuntimeError:
            self._busy = self._scanning = False
            self._error = error_info(StorageError('worker_start_failed'))
            self._message = self._error['title']
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
                    self.items, self.batches, blocked, self._recoveries = value
                    self._message = ('找到未完成批次，請先到「中斷復原」處理。' if self.hasRecovery else
                                     '目前有訂位狀態，請先核對並封存。仍可還原備份。' if blocked
                                     else f'找到 {len(self.items)} 筆可整理紀錄、{len(self.batches)} 個備份批次。')
                elif kind == 'inspect' and not self._cancel.is_set():
                    self._recoveries = value
                    self._message = '找到未完成的紀錄操作，請先核對復原批次。' if value else '沒有未完成的紀錄操作。'
                elif kind == 'mutated':
                    self.items, self.batches = [], []
                    self.selected.clear()
                    self._recoveries = value
                    self._message = '處理完成，請重新掃描查看最新紀錄。官網訂位不變。'
                    self.mutated.emit()
                elif kind == 'error':
                    self.items, self.batches = [], []
                    self.selected.clear()
                    self._error, operations = value
                    if operations is not None:
                        self._recoveries = operations
                    self._message = self._error['title']
                else:
                    self.items, self.batches = [], []
                    self.selected.clear()
                    self._message = ('掃描已取消，沒有移動任何紀錄。' if kind in ('scan', 'inspect', 'cancelled')
                                     else '無法完成，請保留原始紀錄與備份，重新掃描後再試。')
            self.changed.emit()
            if kind != 'progress' and self.hasRecovery:
                self.recoveryFound.emit()

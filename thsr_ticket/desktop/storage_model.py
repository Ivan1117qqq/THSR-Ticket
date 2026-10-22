"""Qt list model with row-level selection updates and constant-time counters."""
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Signal


class StorageRows(QAbstractListModel):
    selectionChanged = Signal()
    rowsChanged = Signal()
    ROLES = {Qt.UserRole + 1: b'recordId', Qt.UserRole + 2: b'dateLabel',
             Qt.UserRole + 3: b'recordBytes', Qt.UserRole + 4: b'chosen'}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.by_id = {}
        self.visible = []
        self.positions = {}
        self.selected = set()
        self.selected_bytes = 0
        self.after = self.before = ''

    def roleNames(self):
        return self.ROLES

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.visible)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.visible):
            return None
        item = self.by_id[self.visible[index.row()]]
        return {Qt.UserRole + 1: item['id'], Qt.UserRole + 2: item['date'],
                Qt.UserRole + 3: item['bytes'], Qt.UserRole + 4: item['id'] in self.selected}.get(role)

    def replace(self, items):
        self.items = items
        self.by_id = {item['id']: item for item in items}
        self.filter(self.after, self.before)

    def filter(self, after, before):
        self.beginResetModel()
        self.after, self.before = after, before
        self.visible = [item['id'] for item in self.items
                        if (not after or item['date'][:10] >= after) and (not before or item['date'][:10] <= before)]
        self.positions = {identifier: index for index, identifier in enumerate(self.visible)}
        self.selected.clear()
        self.selected_bytes = 0
        self.endResetModel()
        self.rowsChanged.emit()
        self.selectionChanged.emit()

    def select(self, identifier, checked):
        if identifier not in self.positions or (identifier in self.selected) == checked:
            return
        if checked:
            self.selected.add(identifier)
            self.selected_bytes += self.by_id[identifier]['bytes']
        else:
            self.selected.remove(identifier)
            self.selected_bytes -= self.by_id[identifier]['bytes']
        index = self.index(self.positions[identifier])
        self.dataChanged.emit(index, index, [Qt.UserRole + 4])
        self.selectionChanged.emit()

    def select_visible(self, checked):
        self.selected = set(self.visible) if checked else set()
        self.selected_bytes = sum(self.by_id[identifier]['bytes'] for identifier in self.selected)
        if self.visible:
            self.dataChanged.emit(self.index(0), self.index(len(self.visible) - 1), [Qt.UserRole + 4])
        self.selectionChanged.emit()

    def snapshot(self):
        return [{**self.by_id[identifier], 'selected': identifier in self.selected} for identifier in self.visible]

    def selected_items(self):
        return [self.by_id[identifier] for identifier in sorted(self.selected)]

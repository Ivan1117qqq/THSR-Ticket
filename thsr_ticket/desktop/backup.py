"""Qt adapter for complete backup previews and exclusive restore to new folders."""
import queue
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from thsr_ticket.backup import preview_source, export_backup, preview_archive, restore_backup
from thsr_ticket.scan_report import ScanCancelled
from thsr_ticket.storage_errors import StorageError, error_info


class BackupManager(QObject):
    changed = Signal()
    notice = Signal(str, bool)

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self._busy = self._cancellable = False
        self._message = '先預覽目前資料，或選擇備份檔進行還原。'
        self._error, self._summary = {}, {}
        self._source = self._archive = None
        self._archive_path = self._target = None
        self._restored = ''
        self._thread = None
        self._queue = queue.Queue()
        self._cancel = threading.Event()

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
    def error(self):
        return self._error

    @Property('QVariantMap', notify=changed)
    def summary(self):
        return self._summary

    @Property(str, notify=changed)
    def archivePath(self):
        return str(self._archive_path or '')

    @Property(str, notify=changed)
    def targetPath(self):
        return str(self._target or '')

    @Property(str, notify=changed)
    def restoredPath(self):
        return self._restored

    @Property(bool, notify=changed)
    def canExport(self):
        return (not self._busy and self._source is not None and not self.context()['dirty']
                and self._source['config'] == self.context()['config'])

    @Property(bool, notify=changed)
    def canRestore(self):
        return not self._busy and self._archive is not None and self._archive['target'] is not None

    @Property(bool, notify=changed)
    def canChooseDestination(self):
        return not self._busy and self._archive is not None

    def invalidate_source(self):
        if not self._busy:
            self._source = None
            self.changed.emit()

    def report_error(self, code):
        self._error = error_info(StorageError(code))
        self._message = self._error['title']
        self.changed.emit()

    @Slot()
    def previewSource(self):
        if self.context()['running']:
            return
        self._source = self._archive = None
        self._summary = {}
        if self.context()['dirty']:
            self._message = '目前有未儲存變更；請先儲存設定，再預覽備份。'
            self._error = {}
            self.changed.emit()
            return
        config = self.context()['config']
        self._launch('source', lambda: preview_source(config, self._cancel))

    @Slot()
    def chooseExport(self):
        if self.context()['running'] or not self.canExport:
            return
        filename = datetime.now().strftime('TravelDesk-Backup-%Y%m%d-%H%M%S') + '.thsr-backup.zip'
        default = self.context()['config'].parent / filename
        target, _ = QFileDialog.getSaveFileName(None, '儲存完整備份', str(default), '完整備份 (*.thsr-backup.zip)')
        if target:
            plan = self._source
            self._launch('export', lambda: export_backup(plan, target))

    @Slot()
    def chooseArchive(self):
        if self.context()['running']:
            return
        path, _ = QFileDialog.getOpenFileName(None, '選擇完整備份', '', '完整備份 (*.thsr-backup.zip)')
        if not path:
            return
        self._archive_path, self._target = Path(path), None
        self._source = self._archive = None
        self._summary, self._restored = {}, ''
        self._preview_archive()

    def _preview_archive(self):
        archive, target = self._archive_path, self._target
        self._archive = None
        self._launch('archive', lambda: preview_archive(archive, target, self._cancel))

    @Slot()
    def chooseDestination(self):
        if self.context()['running'] or self._archive_path is None or self._archive is None:
            return
        parent = QFileDialog.getExistingDirectory(None, '選擇還原父資料夾；程式會建立新的子資料夾')
        if parent:
            self._target = Path(parent) / ('TravelDesk-Restored-' + uuid4().hex[:12])
            self._preview_archive()

    @Slot()
    def applyRestore(self):
        if self.context()['running'] or not self.canRestore:
            return
        plan = self._archive
        self._restored = ''
        self._launch('restore', lambda: restore_backup(plan))

    @Slot()
    def openRestoredFolder(self):
        if self._restored:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self._restored).parent)))

    @Slot()
    def cancel(self):
        if self.cancellable:
            self._cancel.set()
            self._message = '正在取消預覽，請等待讀取結束。'
            self.changed.emit()

    def _launch(self, action, work):
        self._busy = True
        self._cancellable = action in ('source', 'archive')
        self._message = '正在預覽與驗證資料…' if self._cancellable else '正在寫入，請等待完成…'
        self._error = {}
        self._cancel.clear()

        def run():
            try:
                self._queue.put((action, work(), {}))
            except ScanCancelled:
                self._queue.put(('cancelled', None, {}))
            except Exception as error:
                self._queue.put(('error', None, error_info(error)))

        self._thread = threading.Thread(target=run, daemon=False)
        try:
            self._thread.start()
        except RuntimeError:
            self._thread = None
            self._busy = self._cancellable = False
            self.report_error('worker_start_failed')
        self.changed.emit()

    def poll(self):
        if self._thread is None or self._thread.is_alive():
            return
        self._thread.join()
        self._thread = None
        action, value, error = self._queue.get_nowait()
        self._busy = self._cancellable = False
        if error:
            self._source = self._archive = None
            self._error = error
            self._message = error['title']
        elif action in ('source', 'archive') and not self._cancel.is_set():
            self._summary = value['summary']
            self._summary['mode'] = action
            if action == 'source':
                self._source = value
                self._message = '預覽完成，可選擇新的檔名建立完整備份。'
            else:
                self._archive = value
                self._message = ('備份驗證通過，目的位置沒有衝突；確認後可還原。' if self.canRestore else
                                 '備份驗證通過，請選擇還原的父資料夾。')
        elif action == 'export':
            self._message = '完整備份已建立；請妥善保管，未上傳至網路。'
            self._source = None
            self.notice.emit(self._message, False)
        elif action == 'restore':
            self._restored = str(value)
            self._archive = None
            self._message = '已還原到新資料夾，目前設定未切換。請核對原訂位，再載入還原設定。'
            self.notice.emit(self._message, False)
        else:
            self._source = self._archive = None
            self._message = '預覽已取消，未寫入備份或還原資料。'
        self.changed.emit()

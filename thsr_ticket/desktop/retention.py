"""Reviewable permanent cleanup of old query logs."""
from PySide6.QtCore import Slot
from thsr_ticket.desktop.jobs import LocalJob
from thsr_ticket.retention import preview_cleanup, apply_cleanup


class RetentionManager(LocalJob):
    def __init__(self, context, parent=None):
        super().__init__(context, parent)
        self._plan = None
        self._message = '預覽超過保留天數的已結束查票紀錄；訂位結果與封存狀態一律保留。'

    @Slot(int)
    def preview(self, days):
        if self.context()['running']:
            return
        self._plan = None
        config = self.context()['config']
        self.launch('preview', lambda: preview_cleanup(config, days, self._cancel))

    @Slot(bool)
    def apply(self, confirmed):
        if not confirmed or self._plan is None or self.context()['running']:
            return
        plan, self._plan = self._plan, None
        if plan['config'] != self.context()['config']:
            self._result = {}
            self._message = '目前設定已切換，請重新預覽。'
            self.changed.emit()
            return
        self.launch('delete', lambda: apply_cleanup(plan), cancellable=False)

    def completed(self, action, value):
        if action == 'preview':
            self._plan = value
            self._result = {key: value[key] for key in ('days', 'cutoff', 'bytes', 'protected', 'skipped')}
            self._result['count'] = len(value['items'])
            self._result['entries'] = [{key: item[key] for key in ('relative', 'date', 'bytes')}
                                       for item in value['items'][:100]]
            self._result['more'] = max(0, len(value['items']) - 100)
            self._result['preview'] = True
            self._message = '預覽完成；確認後永久刪除，無法由本程式還原。'
        else:
            self._result = {key: value[key] for key in ('status', 'requested', 'deleted', 'bytes_deleted')}
            self._message = f'已清理 {value["deleted"]} 筆、{value["bytes_deleted"]:,} bytes，並保存操作摘要。'
            self.mutated.emit()

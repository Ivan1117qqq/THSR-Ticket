"""Opt-in local task notifications without passenger, journey or booking details."""
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QSystemTrayIcon, QMenu


def task_notification(code, query_only, guard='', phase='prepare'):
    if not query_only and (guard in ('pending', 'unreadable') or code == 'booking_unconfirmed'
                           or (phase in ('submit_ticket', 'parse_result') and code != 'success')):
        return {'title': '訂位結果待確認', 'body': '請回到「我的訂位」核對結果，再進行其他訂位。', 'target': 'records'}
    if code == 'stopped':
        return None
    if code == 'success':
        if query_only:
            return {'title': '查票完成', 'body': '已找到符合車次，請回到任務進度查看。', 'target': 'progress'}
        if guard == 'booked':
            return {'title': '訂位成功 · 尚未付款', 'body': '請回到「我的訂位」查看結果與繳費期限。', 'target': 'records'}
        return {'title': '訂位結果需要核對', 'body': '請先確認本機紀錄與官網結果。', 'target': 'records'}
    if code == 'attempt_limit':
        return {'title': '查詢已結束', 'body': '已達查詢輪數上限，請回到任務進度查看。', 'target': 'progress'}
    return {'title': '任務執行失敗', 'body': '請回到任務進度查看原因與處理建議。', 'target': 'progress'}


class DesktopNotifications(QObject):
    opened = Signal(str)

    def __init__(self, icon, parent=None, tray_factory=QSystemTrayIcon):
        super().__init__(parent)
        self.available = QSystemTrayIcon.isSystemTrayAvailable() and QSystemTrayIcon.supportsMessages()
        self.enabled = False
        self.target = 'progress'
        self.tray = tray_factory(icon, self)
        self.tray.setToolTip('Travel Desk')
        self.tray.messageClicked.connect(lambda: self.opened.emit(self.target))
        self.tray.activated.connect(self.activate)
        self.menu = QMenu()
        self.open_action = QAction('開啟 Travel Desk', self)
        self.open_action.triggered.connect(lambda: self.opened.emit(self.target))
        self.menu.addAction(self.open_action)
        self.tray.setContextMenu(self.menu)

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.tray.setVisible(self.enabled and self.available)

    def activate(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.opened.emit(self.target)

    def publish(self, title, body, target):
        if not self.enabled or not self.available or target not in ('records', 'progress'):
            return
        self.target = target
        self.tray.showMessage(title, body, QSystemTrayIcon.Information, 10000)

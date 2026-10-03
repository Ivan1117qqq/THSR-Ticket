"""One desktop per user data directory; local IPC only requests window activation."""
import hashlib
import os
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QThread, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, directory):
        super().__init__()
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        identity = os.path.normcase(str(directory)).encode('utf-8')
        self.name = 'TravelDesk-' + hashlib.sha256(identity).hexdigest()[:32]
        self.lock = QLockFile(str(directory / 'desktop-instance.lock'))
        # A long-running booking is never stale merely because time has elapsed.
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self._activate)
        self.owner = False

    def start(self):
        if self.lock.tryLock(0):
            self.owner = True
            # Only the lock owner may remove a socket left by a crashed process.
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                self.close()
                raise RuntimeError('無法建立程式協調通道，請稍後再試。')
            return True
        if self.lock.error() != QLockFile.LockFailedError:
            raise RuntimeError('無法建立程式鎖，請確認應用程式資料目錄可寫入。')
        # Allow the first process to finish starting its local listener.
        for _ in range(20):
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(100):
                socket.disconnectFromServer()
                return False
            socket.abort()
            QThread.msleep(50)
        raise RuntimeError('Travel Desk 已啟動或正在關閉，請切回原視窗；若無回應，請稍後再試。')

    def _activate(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.close()
            socket.deleteLater()
            self.activated.emit()

    def close(self):
        if self.owner:
            self.server.close()
            self.lock.unlock()
            self.owner = False


def activate_window(window):
    if window.isMinimized():
        window.showNormal()
    else:
        window.show()
    window.raise_()
    window.requestActivate()

import os
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402
from thsr_ticket.desktop.single_instance import SingleInstance, activate_window  # noqa: E402


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_second_process_activates_owner_and_clean_restart(app, tmp_path):
    owner = SingleInstance(tmp_path)
    activated = []
    owner.activated.connect(lambda: activated.append(True))
    assert owner.start()
    try:
        code = ('import sys; from PySide6.QtCore import QCoreApplication; '
                'from thsr_ticket.desktop.single_instance import SingleInstance; '
                'app=QCoreApplication([]); instance=SingleInstance(sys.argv[1]); '
                'print(instance.start()); instance.close()')
        reply = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
                               capture_output=True, text=True, timeout=10)
        assert reply.returncode == 0, reply.stderr
        assert reply.stdout.strip() == 'False'
        for _ in range(20):
            app.processEvents()
            if activated:
                break
            time.sleep(0.01)
        assert activated == [True]
        assert owner.owner
    finally:
        owner.close()
    replacement = SingleInstance(tmp_path)
    try:
        assert replacement.start()
    finally:
        replacement.close()


def test_crashed_process_does_not_block_restart(app, tmp_path):
    ready = tmp_path / 'ready'
    code = ('import sys,time; from pathlib import Path; from PySide6.QtCore import QCoreApplication; '
            'from thsr_ticket.desktop.single_instance import SingleInstance; '
            'app=QCoreApplication([]); instance=SingleInstance(sys.argv[1]); '
            'assert instance.start(); Path(sys.argv[2]).write_text("ready"); time.sleep(30)')
    child = subprocess.Popen([sys.executable, '-c', code, str(tmp_path), str(ready)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
    finally:
        child.kill()
        child.wait(timeout=5)
    replacement = SingleInstance(tmp_path)
    try:
        assert replacement.start()
    finally:
        replacement.close()


def test_listener_failure_releases_lock(app, tmp_path, monkeypatch):
    owner = SingleInstance(tmp_path)
    monkeypatch.setattr(owner.server, 'listen', lambda name: False)
    with pytest.raises(RuntimeError):
        owner.start()
    replacement = SingleInstance(tmp_path)
    try:
        assert replacement.start()
    finally:
        replacement.close()


@pytest.mark.parametrize('state', [Qt.WindowNoState, Qt.WindowMinimized, Qt.WindowMaximized])
def test_activation_preserves_normal_window_state(state):
    window = Mock(spec=QQuickWindow)
    window.windowState.return_value = state
    activate_window(window)
    assert window.showNormal.call_count == int(state == Qt.WindowMinimized)
    assert window.setVisible.call_count == int(state != Qt.WindowMinimized)
    window.raise_.assert_called_once()
    window.requestActivate.assert_called_once()


@pytest.mark.parametrize('state', [Qt.WindowNoState, Qt.WindowMinimized, Qt.WindowMaximized])
def test_activation_with_real_quick_window_uses_qwindow_api(app, state):
    window = QQuickWindow()
    try:
        window.setWindowState(state)
        activate_window(window)
        app.processEvents()
        expected = Qt.WindowNoState if state == Qt.WindowMinimized else state
        assert window.windowState() == expected and window.isVisible()
    finally:
        window.close()

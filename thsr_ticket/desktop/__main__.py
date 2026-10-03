"""Launch with python -m thsr_ticket.desktop."""
import sys
import argparse
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6 import QtSvg  # noqa: F401 - include SVG icon plugin in the desktop bundle

from thsr_ticket.desktop.controller import DesktopController
from thsr_ticket.version import VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', metavar='REPORT', help='Offline package check; no user config or booking')
    args = parser.parse_args()
    # Installer checks this named object and refuses upgrades while the application is open.
    mutex = None
    if sys.platform == 'win32' and not args.self_test:
        import ctypes
        from ctypes import wintypes
        create_mutex = ctypes.windll.kernel32.CreateMutexW
        create_mutex.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        create_mutex.restype = wintypes.HANDLE
        mutex = create_mutex(None, False, 'TravelDeskRunning')
    QQuickStyle.setStyle('Basic')
    app = QApplication(sys.argv)
    app.setOrganizationName('THSRTicket')
    app.setApplicationName('TravelDesk')
    app.setApplicationVersion(VERSION)
    app.setWindowIcon(QIcon(str(Path(__file__).parent / 'assets' / 'app.svg')))
    temporary = tempfile.TemporaryDirectory(prefix='travel-desk-test-') if args.self_test else None
    controller = DesktopController(temporary.name if temporary else
                                   QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    engine.setInitialProperties({'backend': controller, 'visible': not bool(args.self_test)})
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / 'qml' / 'Main.qml')))
    if not engine.rootObjects():
        return 1
    if args.self_test:
        from thsr_ticket.captcha import CaptchaReader
        from playwright.sync_api import sync_playwright
        report = {'qml': True, 'warnings': warnings}
        try:
            for page in range(5):
                controller.navigate(page)
                app.processEvents()
            report['ocr_standard'] = CaptchaReader(model='standard').prepare()
            report['ocr_beta'] = CaptchaReader(model='beta').prepare()
            with sync_playwright() as driver:
                report['playwright_driver'] = bool(driver.chromium.name)
            if sys.platform == 'win32':
                from thsr_ticket.config_store import write_config_data, read_config_data
                protected = Path(temporary.name) / 'privacy-test.json'
                demo = {'personal_id': 'TEST-PRIVATE', 'phone_num': '0000000000'}
                write_config_data(protected, demo, protect=True)
                report['private_storage'] = read_config_data(protected) == demo and \
                    'TEST-PRIVATE' not in protected.read_text(encoding='utf-8')
        except Exception as exc:
            report['error_type'] = type(exc).__name__
        Path(args.self_test).write_text(json.dumps(report, indent=2), encoding='utf-8')
        controller.timer.stop()
        temporary.cleanup()
        required = ['qml', 'ocr_standard', 'ocr_beta', 'playwright_driver']
        if sys.platform == 'win32':
            required.append('private_storage')
        return 0 if all(report.get(key) for key in required) \
            and not warnings and 'error_type' not in report else 1
    controller.closeReady.connect(app.quit)
    result = app.exec()
    if mutex:
        close_handle = ctypes.windll.kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle(mutex)
    return result


if __name__ == '__main__':
    sys.exit(main())

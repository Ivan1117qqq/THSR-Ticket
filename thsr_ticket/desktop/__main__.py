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

from thsr_ticket.desktop.controller import DesktopController


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', metavar='REPORT', help='Offline package check; no user config or booking')
    args = parser.parse_args()
    QQuickStyle.setStyle('Basic')
    app = QApplication(sys.argv)
    app.setOrganizationName('THSRTicket')
    app.setApplicationName('TravelDesk')
    app.setApplicationVersion('0.2.0')
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
        except Exception as exc:
            report['error_type'] = type(exc).__name__
        Path(args.self_test).write_text(json.dumps(report, indent=2), encoding='utf-8')
        controller.timer.stop()
        temporary.cleanup()
        return 0 if all(report.get(key) for key in ('qml', 'ocr_standard', 'ocr_beta', 'playwright_driver')) \
            and not warnings and 'error_type' not in report else 1
    controller.closeReady.connect(app.quit)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())

"""Render the actual QML with synthetic data; never read user settings or book tickets.

Run from repository root: python -m scripts.preview_desktop --scale 1.25
"""
import argparse
import os
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scale', default='1')
    parser.add_argument('--output', default='build/preview')
    args = parser.parse_args()
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    os.environ['QT_SCALE_FACTOR'] = args.scale
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle
    from thsr_ticket.desktop.controller import DesktopController

    QQuickStyle.setStyle('Basic')
    app = QApplication([])
    for name in ('msjh.ttc', 'msjhbd.ttc'):
        path = Path('C:/Windows/Fonts') / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='travel-preview-') as temporary:
        controller = DesktopController(temporary)
        controller._form['personal_id'] = 'DEMO123456'
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda errors: warnings.extend(str(error) for error in errors))
        engine.setInitialProperties({'backend': controller})
        qml = Path(__file__).resolve().parents[1] / 'thsr_ticket/desktop/qml/Main.qml'
        engine.load(QUrl.fromLocalFile(str(qml)))
        if not engine.rootObjects():
            raise RuntimeError(warnings)
        window = engine.rootObjects()[0]
        window.resize(1080, 720)
        for page in range(5):
            controller.navigate(page)
            controller._records = [{'status': 'booked', 'code': 'DEMO1234', 'current': True,
                                    'ticket': {'start_station': '台北', 'dest_station': '台中',
                                               'date': '示範日期', 'depart_time': '09:31', 'train_id': '0117',
                                               'seat': '9 車 3E', 'price': 'TWD 700',
                                               'payment_deadline': '示範期限', 'ticket_num_info': '成人 1 張'}}]
            controller.changed.emit()
            for _ in range(30):
                app.processEvents()
            frame = window.grabWindow()
            if not frame.save(str(destination / f'page-{page}-scale-{args.scale}.png')):
                raise RuntimeError('Failed to save preview')
        window.setProperty('allowClose', True)
        window.close()
        controller.timer.stop()
        if warnings:
            raise RuntimeError(warnings)


if __name__ == '__main__':
    main()

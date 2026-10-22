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
    from PySide6.QtCore import QUrl, QObject, QMetaObject
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
        controller.prepareDiagnostics()
        from thsr_ticket.booking_records import record_paths
        _, preview_runs = record_paths(controller.path)
        for identifier in ('a' * 32, 'b' * 32):
            directory = preview_runs / identifier
            directory.mkdir(parents=True)
            (directory / 'events.jsonl').write_bytes(b'{"event":"run_finished"}\n')
        batch = preview_runs.parent / (preview_runs.name + '.history-backups') / ('c' * 32) / ('d' * 32)
        batch.mkdir(parents=True)
        (batch / 'events.jsonl').write_bytes(b'{"event":"run_finished"}\n')
        controller.prepareStorage()
        controller.storage._thread.join(timeout=5)
        controller.storage.poll()
        QMetaObject.invokeMethod(window.findChild(QObject, 'storageDialog'), 'open')
        for _ in range(30):
            app.processEvents()
        if not window.grabWindow().save(str(destination / f'storage-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save storage preview')
        window.findChild(QObject, 'storageTabs').setProperty('currentIndex', 1)
        for _ in range(30):
            app.processEvents()
        if not window.grabWindow().save(str(destination / f'backups-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save backup preview')
        from thsr_ticket.run_records import atomic_json, timestamp
        from thsr_ticket.storage_journal import directory_signature
        journal_root = preview_runs.parent / (preview_runs.name + '.operations')
        journal_root.mkdir()
        atomic_json(journal_root / ('f' * 32 + '.json'), {
            'version': 1, 'status': 'pending', 'action': 'move', 'batch': 'e' * 32,
            'entries': [directory_signature(preview_runs / ('a' * 32))], 'created_at': timestamp(),
        })
        controller.prepareStorage()
        controller.storage._thread.join(timeout=5)
        controller.storage.poll()
        for _ in range(30):
            app.processEvents()
        if not window.grabWindow().save(str(destination / f'interrupted-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save interrupted operation preview')
        from thsr_ticket.storage_errors import error_info
        controller.storage._error = error_info(PermissionError())
        controller.storage._message = controller.storage.error['title']
        controller.storage.changed.emit()
        for _ in range(30):
            app.processEvents()
        if not window.grabWindow().save(str(destination / f'storage-error-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save storage error preview')
        QMetaObject.invokeMethod(window.findChild(QObject, 'storageDialog'), 'close')
        QMetaObject.invokeMethod(window.findChild(QObject, 'diagnosticDialog'), 'open')
        for _ in range(30):
            app.processEvents()
        if not window.grabWindow().save(str(destination / f'diagnostics-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save diagnostics preview')
        QMetaObject.invokeMethod(window.findChild(QObject, 'diagnosticDialog'), 'close')
        demo_record = controller._records[0]
        controller.navigate(3)
        controller._records = [demo_record]
        controller.changed.emit()
        window.setProperty('selected', demo_record)
        QMetaObject.invokeMethod(window.findChild(QObject, 'cancellationDialog'), 'open')
        for _ in range(30):
            app.processEvents()
        if not window.grabWindow().save(str(destination / f'cancel-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save cancellation preview')
        QMetaObject.invokeMethod(window.findChild(QObject, 'cancellationDialog'), 'close')
        controller.navigate(0)
        controller._guard = 'pending'
        controller.changed.emit()
        for _ in range(30):
            app.processEvents()
        if not window.grabWindow().save(str(destination / f'recovery-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save recovery preview')
        window.setProperty('allowClose', True)
        window.close()
        controller.timer.stop()
        if warnings:
            raise RuntimeError(warnings)


if __name__ == '__main__':
    main()

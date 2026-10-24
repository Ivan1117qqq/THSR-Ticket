"""Render the actual QML with synthetic data; never read user settings or book tickets.

Run from repository root: python -m scripts.preview_desktop --scale 1.25
"""
import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta
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
    from PySide6.QtTest import QTest
    from shiboken6 import delete as delete_qml
    from thsr_ticket.desktop.controller import DesktopController
    from thsr_ticket.automation import TAIPEI
    from thsr_ticket.journey_planning import PlanningIndex

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
        while controller._record_loader.busy:
            controller._record_loader._thread.join(timeout=5)
            controller._record_loader.poll()
        controller.tools.set_notification_support(True)
        controller.tools.setNotifications(True)
        controller._form['personal_id'] = 'DEMO123456'
        preview_now = datetime.now(TAIPEI)
        preview_day = (preview_now + timedelta(days=2)).date().isoformat()
        controller.planner.clock = lambda: preview_now
        controller.planner.saveTemplate('週末返家', controller.form, '')
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
            while controller._record_loader.busy:
                controller._record_loader._thread.join(timeout=5)
                controller._record_loader.poll()
            controller._records = [{'status': 'booked', 'code': 'DEMO1234', 'current': True,
                                    'ticket': {'start_station': '台北', 'dest_station': '台中',
                                               'date': preview_day, 'depart_time': '09:31', 'train_id': '0117',
                                               'seat': '9 車 3E', 'price': 'TWD 700',
                                               'payment_deadline': (preview_now + timedelta(hours=2)).strftime(
                                                   '%Y-%m-%d %H:%M'), 'ticket_num_info': '成人 1 張'}}]
            controller.planner.update_records(controller.path, PlanningIndex(controller._records))
            controller.planner.selectDate(preview_day)
            controller._record_loader.report = {'accepted': 1, 'skipped': 0, 'failed': 0, 'reasons': []}
            controller.changed.emit()
            for _ in range(30):
                app.processEvents()
            frame = window.grabWindow()
            if not frame.save(str(destination / f'page-{page}-scale-{args.scale}.png')):
                raise RuntimeError('Failed to save preview')
            if page == 0:
                viewport = window.findChild(QObject, 'overviewPage').property('contentItem')
                calendar = window.findChild(QObject, 'journeyCalendarCard')
                from PySide6.QtCore import QPointF
                point = calendar.mapToItem(viewport.property('contentItem'), QPointF(0, 0))
                viewport.setProperty('contentY', point.y() - 8)
                QTest.qWait(100)
                if not window.grabWindow().save(str(destination / f'agenda-scale-{args.scale}.png')):
                    raise RuntimeError('Failed to save agenda preview')
                viewport.setProperty('contentY', 0)
        QMetaObject.invokeMethod(window.findChild(QObject, 'templateDialog'), 'open')
        QTest.qWait(180)
        window.findChild(QObject, 'templateList').setProperty('currentIndex', 0)
        QTest.qWait(100)
        if not window.grabWindow().save(str(destination / f'templates-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save templates preview')
        QMetaObject.invokeMethod(window.findChild(QObject, 'templateDialog'), 'close')
        QTest.qWait(180)
        dual_dialog = window.findChild(QObject, 'dualRailDialog')
        QMetaObject.invokeMethod(dual_dialog, 'open')
        QTest.qWait(180)
        if not window.grabWindow().save(str(destination / f'dual-rail-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save dual rail preview')
        QMetaObject.invokeMethod(dual_dialog, 'close')
        QTest.qWait(180)
        deadline_dialog = window.findChild(QObject, 'deadlineDialog')
        deadline_dialog.setProperty('record', controller.planner.agenda['items'][0])
        window.findChild(QObject, 'localDeadlineInput').setProperty(
            'text', (preview_now + timedelta(hours=2)).strftime('%Y-%m-%d %H:%M'))
        QMetaObject.invokeMethod(deadline_dialog, 'open')
        QTest.qWait(180)
        if not window.grabWindow().save(str(destination / f'deadline-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save deadline preview')
        QMetaObject.invokeMethod(deadline_dialog, 'close')
        QTest.qWait(180)
        controller.navigate(1)
        original_date = controller.form['outbound_date']
        controller.setField('outbound_date', '2024-02-29')
        for key in ('outbound_date', 'start_at'):
            QMetaObject.invokeMethod(window.findChild(QObject, 'calendar_' + key), 'clicked')
            QTest.qWait(180)
            if not window.grabWindow().save(str(destination / f'date-{key}-scale-{args.scale}.png')):
                raise RuntimeError('Failed to save date picker preview')
            QMetaObject.invokeMethod(window.findChild(QObject, 'datePicker_' + key), 'close')
            QTest.qWait(180)
        controller.setField('outbound_date', original_date)
        controller.navigate(4)
        for section in range(3):
            window.findChild(QObject, 'settingsPage').setProperty('section', section)
            for _ in range(30):
                app.processEvents()
            if not window.grabWindow().save(str(destination / f'settings-{section}-scale-{args.scale}.png')):
                raise RuntimeError('Failed to save settings preview')
        demo_record = controller._records[0]
        controller.tools.prepareDiagnostics()
        from thsr_ticket.booking_records import record_paths
        _, preview_runs = record_paths(controller.path)
        for identifier in ('a' * 32, 'b' * 32):
            directory = preview_runs / identifier
            directory.mkdir(parents=True)
            (directory / 'events.jsonl').write_bytes(b'{"event":"run_finished"}\n')
        batch = preview_runs.parent / (preview_runs.name + '.history-backups') / ('c' * 32) / ('d' * 32)
        batch.mkdir(parents=True)
        (batch / 'events.jsonl').write_bytes(b'{"event":"run_finished"}\n')
        malformed = preview_runs / ('1' * 32)
        malformed.mkdir()
        (malformed / 'events.jsonl').write_bytes(b'broken')
        unfinished = preview_runs / ('2' * 32)
        unfinished.mkdir()
        (unfinished / 'events.jsonl').write_bytes(b'{"event":"run_started"}\n')
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
        history_path = preview_runs / ('3' * 32) / 'events.jsonl'
        history_path.parent.mkdir()
        demo_events = [
            {'event': 'run_started', 'app_version': '0.4.0', 'query_only': True},
            {'event': 'stage', 'phase': 'query'},
            {'event': 'task_completed', 'outcome': 'network', 'phase': 'query'},
        ]
        history_path.write_text(''.join(json.dumps(event) + '\n' for event in demo_events), encoding='utf-8')
        controller.tools.prepareHistory()
        controller.tools.historyDiagnostics._thread.join(timeout=5)
        controller.tools.historyDiagnostics.poll()
        controller.tools.historyDiagnostics.select('runs/' + '3' * 32)
        QMetaObject.invokeMethod(window.findChild(QObject, 'historyDiagnosticsDialog'), 'open')
        for _ in range(30):
            app.processEvents()
        if not window.grabWindow().save(str(destination / f'history-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save history preview')
        controller.tools.prepareHistoricalDiagnostics()
        QMetaObject.invokeMethod(window.findChild(QObject, 'diagnosticDialog'), 'open')
        for _ in range(30):
            app.processEvents()
        if not window.grabWindow().save(str(destination / f'history-export-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save history export preview')
        QMetaObject.invokeMethod(window.findChild(QObject, 'diagnosticDialog'), 'close')
        QMetaObject.invokeMethod(window.findChild(QObject, 'historyDiagnosticsDialog'), 'close')
        controller.navigate(3)
        while controller._record_loader.busy:
            controller._record_loader._thread.join(timeout=5)
            controller._record_loader.poll()
        controller._records = [demo_record]
        controller.changed.emit()
        window.findChild(QObject, 'bookingActions').setProperty('selected', demo_record)
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
        controller.navigate(4)
        window.findChild(QObject, 'settingsPage').setProperty('section', 1)
        controller._form['personal_id'] = 'A123456789'
        controller.save()
        manager = controller.backup
        manager.previewSource()
        manager._thread.join(timeout=5)
        assert not manager._thread.is_alive()
        manager.poll()
        assert manager.canExport
        QMetaObject.invokeMethod(window.findChild(QObject, 'backupDialog'), 'open')
        for _ in range(30):
            app.processEvents()
        QTest.qWait(160)
        if not window.grabWindow().save(str(destination / f'full-backup-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save full backup preview')
        from thsr_ticket.backup import export_backup
        backup_archive = Path(temporary) / 'preview.thsr-backup.zip'
        export_backup(manager._source, backup_archive)
        manager._source = None
        manager._archive_path = backup_archive
        manager._target = Path(temporary) / 'restored-preview'
        manager._preview_archive()
        manager._thread.join(timeout=5)
        assert not manager._thread.is_alive()
        manager.poll()
        window.findChild(QObject, 'backupTabs').setProperty('currentIndex', 1)
        for _ in range(30):
            app.processEvents()
        QTest.qWait(160)
        if not window.grabWindow().save(str(destination / f'full-restore-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save full restore preview')
        manager.applyRestore()
        manager._thread.join(timeout=5)
        assert not manager._thread.is_alive()
        manager.poll()
        assert manager.restoredPath
        for _ in range(30):
            app.processEvents()
        QTest.qWait(160)
        if not window.grabWindow().save(str(destination / f'full-restored-scale-{args.scale}.png')):
            raise RuntimeError('Failed to save restored preview')
        QMetaObject.invokeMethod(window.findChild(QObject, 'backupDialog'), 'close')
        management = controller.management
        management._snapshot = {'code': '12345678', 'status': 'unpaid', 'trip_matches': True,
                                'verified_at': '2099-01-15T08:00:00+08:00',
                                'ticket': {'date': '2099-01-15', 'train_id': '0117',
                                           'start_station': '台北', 'dest_station': '台中'}}
        management._stage, management._message = 'review', '假資料示範：核對這筆訂位，再決定是否取消。'
        management.changed.emit()
        controller.retention._result = {'preview': True, 'count': 3, 'bytes': 8500025, 'days': 90,
                                        'cutoff': '2098-10-15 08:00:00', 'protected': 2, 'skipped': 1,
                                        'entries': [{'relative': 'booking.local.runs/' + str(i) * 32,
                                                     'date': '2098-09-15 08:00:00', 'bytes': 2833341}
                                                    for i in (1, 2, 3)]}
        controller.retention.changed.emit()
        metrics = {'samples': 100, 'exact_match_rate': 0.85, 'coverage': 0.9,
                   'accepted_accuracy': 85 / 90, 'mean_inference_ms': 23.5}
        controller.ocrLab._result = {'models': {'standard': metrics, 'beta': metrics}}
        controller.ocrLab.changed.emit()
        for name in ('managementDialog', 'retentionDialog', 'ocrLabDialog'):
            popup = window.findChild(QObject, name)
            QMetaObject.invokeMethod(popup, 'open')
            for _ in range(30):
                app.processEvents()
            QTest.qWait(160)
            if not window.grabWindow().save(str(destination / f'{name}-scale-{args.scale}.png')):
                raise RuntimeError('Failed to save feature preview')
            QMetaObject.invokeMethod(popup, 'close')
        window.setProperty('allowClose', True)
        window.close()
        controller.timer.stop()
        controller.storage._timer.stop()
        delete_qml(engine)
        if warnings:
            raise RuntimeError(warnings)


if __name__ == '__main__':
    main()

"""Measure real offscreen QML rendering plus bounded large-log inspection on fake data."""
import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from statistics import median


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='build/desktop-performance.json')
    args = parser.parse_args()
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtCore import QUrl, QObject, QTimer
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtTest import QTest
    from shiboken6 import delete
    from thsr_ticket.desktop.controller import DesktopController
    from thsr_ticket.record_storage import inspect_run, RunSkipped
    from thsr_ticket.record_search import RecordSearchIndex
    from thsr_ticket.version import VERSION

    QQuickStyle.setStyle('Basic')
    app = QApplication([])
    for name in ('msjh.ttc', 'msjhbd.ttc'):
        font = Path('C:/Windows/Fonts') / name
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    warnings, results = [], []
    with tempfile.TemporaryDirectory(prefix='thsr-performance-') as folder:
        print('Creating isolated QML scene', flush=True)
        controller = DesktopController(folder)
        while controller._record_loader.busy:
            controller._record_loader._thread.join()
            controller._record_loader.poll()
        engine = QQmlApplicationEngine()
        engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
        engine.setInitialProperties({'backend': controller})
        path = Path(__file__).resolve().parents[1] / 'thsr_ticket/desktop/qml/Main.qml'
        engine.load(QUrl.fromLocalFile(str(path)))
        if not engine.rootObjects():
            raise RuntimeError('QML did not load')
        window = engine.rootObjects()[0]
        window.resize(1080, 720)
        controller.navigate(3)
        window.findChild(QObject, 'includeHistoryCheck').setProperty('checked', True)
        heartbeat = []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: heartbeat.append(time.perf_counter()))
        timer.start()
        for count in (100, 1000, 10000):
            print(f'Measuring {count} records', flush=True)
            QTest.qWait(30)
            heartbeat.clear()
            heartbeat.append(time.perf_counter())
            started = time.perf_counter()
            controller._records = [{'code': f'{index:08d}', 'status': 'history', 'current': False,
                                    'ticket': {'date': '2099-01-15', 'train_id': '0117',
                                               'start_station': '台北', 'dest_station': '台中'}}
                                   for index in range(count)]
            prepared_at = time.perf_counter()
            controller._record_search = RecordSearchIndex(controller._records)
            index_ms = (time.perf_counter() - prepared_at) * 1000
            controller.changed.emit()
            app.processEvents()
            frame = window.grabWindow()
            if frame.isNull():
                raise RuntimeError('QML frame unavailable')
            render_ms = (time.perf_counter() - started) * 1000
            QTest.qWait(100)
            cards = window.findChild(QObject, 'bookingCards').property('count')
            assert cards == 25
            gaps = [(b - a) * 1000 for a, b in zip(heartbeat, heartbeat[1:])]
            index = controller._record_search
            filtered_at = time.perf_counter()
            first = controller.recordPageData(True, '台中', '', 0, 0)
            first_search_ms = (time.perf_counter() - filtered_at) * 1000
            cached_ms = []
            for page in range(100):
                cached_at = time.perf_counter()
                data = controller.recordPageData(True, '台中', '', 0, page)
                cached_ms.append((time.perf_counter() - cached_at) * 1000)
                assert len(data['items']) <= 25
            assert first['total'] == count
            passes = index.filter_passes
            search = window.findChild(QObject, 'bookingSearch')
            for text in ('台', '台北', '台', '台北'):
                search.setProperty('text', text)
                app.processEvents()
            QTest.qWait(350)
            assert index.filter_passes == passes + 1
            search.setProperty('text', '')
            app.processEvents()
            results.append({'records': count, 'rendered_cards': cards, 'update_and_grab_ms': round(render_ms, 2),
                            'max_heartbeat_gap_ms': round(max(gaps, default=0), 2),
                            'index_preparation_ms': round(index_ms, 2),
                            'first_nonempty_search_ms': round(first_search_ms, 3),
                            'cached_page_median_ms': round(median(cached_ms), 3),
                            'typing_burst_filter_passes': index.filter_passes - passes,
                            'search_delay_ms': 250})
        timer.stop()
        print('Measuring large log', flush=True)
        logs = Path(folder) / ('a' * 32)
        logs.mkdir()
        line = b'{"event":"stage","phase":"query"}\n'
        with (logs / 'events.jsonl').open('wb') as handle:
            handle.write(line * 250000 + b'{"event":"run_finished"}\n')
        started = time.perf_counter()
        inspected = inspect_run(logs)
        log_ms = (time.perf_counter() - started) * 1000
        (logs / 'events.jsonl').write_bytes(b'x' * (1024 * 1024 + 1))
        try:
            inspect_run(logs)
        except RunSkipped:
            oversized_line_rejected = True
        else:
            oversized_line_rejected = False
        controller.timer.stop()
        controller.storage._timer.stop()
        window.setProperty('allowClose', True)
        window.close()
        delete(engine)
    if warnings:
        raise RuntimeError(warnings)
    report = {'app_version': VERSION, 'scope': 'synthetic offscreen rendering; not live desktop latency',
              'qml': results, 'large_log_bytes': inspected['bytes'], 'large_log_scan_ms': round(log_ms, 2),
              'oversized_line_rejected': oversized_line_rejected, 'qml_warnings': warnings}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

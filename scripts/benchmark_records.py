"""Measure local synthetic record scans, selected validation and Qt list updates."""
import argparse
import json
import platform
import tempfile
import time
from pathlib import Path


def measure(count, root, app):
    from thsr_ticket.booking_records import record_paths
    from thsr_ticket.desktop.record_loader import RecordLoader
    from thsr_ticket.desktop.storage_model import StorageRows
    from thsr_ticket.record_storage import inventory, move_history, restore_history
    from thsr_ticket.scan_report import ScanReport
    import thsr_ticket.record_storage as storage

    config = root / 'benchmark.json'
    _, runs = record_paths(config)
    for index in range(count):
        directory = runs / f'{index:032x}'
        directory.mkdir(parents=True)
        (directory / 'events.jsonl').write_bytes(b'{"event":"run_finished"}\n')
        (directory / 'result.json').write_text(json.dumps({'tickets': [{'id': f'DEMO{index:08d}'}]}), encoding='utf-8')
    started = time.perf_counter()
    report = ScanReport()
    items = inventory(config, report=report)
    scan_ms = (time.perf_counter() - started) * 1000
    inspected = []
    inspect = storage.inspect_run

    def inspect_selected(directory, cancel=None):
        inspected.append(directory.name)
        return inspect(directory, cancel)

    storage.inspect_run = inspect_selected
    started = time.perf_counter()
    try:
        backup = move_history(config, [items[0]])
    finally:
        storage.inspect_run = inspect
    move_ms = (time.perf_counter() - started) * 1000
    restore_history(config, backup)
    model = StorageRows()
    model.replace(items)
    resets, row_updates = [], []
    model.modelReset.connect(lambda: resets.append(True))
    model.dataChanged.connect(lambda *args: row_updates.append(True))
    started = time.perf_counter()
    for _ in range(1000):
        model.select(items[0]['id'], True)
        model.select(items[0]['id'], False)
    selection_ms = (time.perf_counter() - started) * 1000
    loader = RecordLoader()
    loaded = []
    loader.loaded.connect(lambda config, entries, error: loaded.append((len(entries), error)))
    started = time.perf_counter()
    loader.request(config)
    ui_cycles = 0
    deadline = time.monotonic() + 60
    while loader.busy:
        app.processEvents()
        loader.poll()
        ui_cycles += 1
        if time.monotonic() > deadline:
            loader.cancel()
            raise RuntimeError('Background benchmark timed out')
        time.sleep(0.001)
    load_ms = (time.perf_counter() - started) * 1000
    assert loaded == [(count, {})]
    assert len(inspected) == 1 and not resets and len(row_updates) == 2000
    return {'records': count, 'scan_ms': round(scan_ms, 2), 'scan_report': report.snapshot(),
            'selected_move_ms': round(move_ms, 2), 'revalidated_records': len(inspected),
            'toggle_2000_ms': round(selection_ms, 2), 'model_resets_during_selection': len(resets),
            'row_update_signals': len(row_updates), 'background_load_ms': round(load_ms, 2),
            'ui_event_cycles_during_load': ui_cycles}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--counts', nargs='+', type=int, default=[100, 1000])
    parser.add_argument('--output', default='build/record-benchmark.json')
    args = parser.parse_args()
    if any(not 1 <= count <= 10000 for count in args.counts):
        parser.error('counts must be between 1 and 10000')
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for count in args.counts:
        with tempfile.TemporaryDirectory(prefix='synthetic-records-', dir=output.parent) as directory:
            results.append(measure(count, Path(directory), app))
    value = {'scope': 'synthetic local records only; no live booking or user data',
             'platform': platform.system(), 'python': platform.python_version(), 'results': results}
    output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()

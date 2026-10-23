"""Reversible history cleanup. Never remove the submission guard or unknown files."""
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from thsr_ticket.booking_records import record_paths
from thsr_ticket.record_lock import record_lock
from thsr_ticket.record_schema import validate_record, RecordVersionError
from thsr_ticket.scan_report import ScanReport, check_cancel
from thsr_ticket.scan_report import ScanCancelled as ScanCancelled
from thsr_ticket.storage_errors import StorageError
from thsr_ticket.storage_journal import (
    execute, require_resolved, directory_signature, incomplete_batches, pending_operations,
)

__all__ = ['inventory', 'move_history', 'restore_history', 'latest_backup', 'backup_batches', 'ScanCancelled']
BOOKING_PHASES = {'select_train', 'submit_ticket', 'parse_result', 'save_result'}


def linked(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


class RunSkipped(ValueError):
    def __init__(self, reason):
        self.reason = reason


def inspect_run(directory, cancel=None, query_only=False):
    check_cancel(cancel)
    if linked(directory):
        raise RunSkipped('linked')
    if not directory.is_dir():
        raise RunSkipped('unsupported')
    files = sorted(directory.iterdir())
    if any(linked(p) for p in files):
        raise RunSkipped('linked')
    if not files or any(not p.is_file() or p.name not in ('events.jsonl', 'result.json') for p in files):
        raise RunSkipped('unsupported')
    if not any(p.name == 'events.jsonl' for p in files):
        raise RunSkipped('unfinished')
    digest, size, last = hashlib.sha256(), 0, {}
    query_started, booking_activity = False, False
    for path in files:
        digest.update(path.name.encode() + b'\0')
        with path.open('rb') as handle:
            if path.name == 'events.jsonl':
                for line in iter(lambda: handle.readline(1024 * 1024 + 1), b''):
                    check_cancel(cancel)
                    if len(line) > 1024 * 1024:
                        raise RunSkipped('unsupported')
                    digest.update(line)
                    size += len(line)
                    last = validate_record(json.loads(line))
                    if query_only:
                        if last.get('event') == 'run_started':
                            query_started = True
                            booking_activity |= last.get('query_only') is not True
                        booking_activity |= (last.get('phase') in BOOKING_PHASES or
                                             last.get('event') in ('result_save_failed', 'state_update_failed') or
                                             last.get('reason') == 'booking_unconfirmed' or
                                             last.get('outcome') in ('booked', 'booking_unconfirmed'))
            else:
                content = handle.read(8 * 1024 * 1024 + 1)
                if len(content) > 8 * 1024 * 1024:
                    raise RunSkipped('unsupported')
                check_cancel(cancel)
                digest.update(content)
                size += len(content)
                validate_record(json.loads(content))
    if last.get('event') not in ('run_finished', 'run_stopped', 'task_completed'):
        raise RunSkipped('unfinished')
    if query_only and (not query_started or booking_activity):
        raise RunSkipped('unsupported')
    date = datetime.fromtimestamp((directory / 'events.jsonl').stat().st_mtime, timezone(timedelta(hours=8)))
    return {'id': directory.name, 'bytes': size, 'digest': digest.hexdigest(),
            'date': date.strftime('%Y-%m-%d %H:%M:%S')}


def inventory(config_path, cancel=None, progress=None, report=None):
    state, runs = record_paths(config_path)
    report = report if report is not None else ScanReport()
    if linked(runs):
        raise StorageError('unsafe_path')
    if state.exists() or pending_operations(config_path):
        return []
    items = []
    try:
        directories = runs.iterdir()
        for index, directory in enumerate(directories):
            check_cancel(cancel)
            if progress and index % 20 == 0:
                progress(index)
            if directory.name == 'archives':
                continue  # A separate record type, outside this cleanup scope.
            try:
                if not re.fullmatch('[0-9a-f]{32}', directory.name):
                    raise RunSkipped('unsupported')
                item = inspect_run(directory, cancel)
            except RunSkipped as error:
                report.skip(error.reason)
            except RecordVersionError:
                report.skip('version')
            except (ValueError, UnicodeError):
                report.skip('malformed')
            except OSError as error:
                report.failure(error)
            else:
                items.append(item)
                report.accepted += 1
    except FileNotFoundError:
        if runs.exists():
            raise
    return sorted(items, key=lambda item: item['id'])


def move_history(config_path, expected):
    state, runs = record_paths(config_path)
    with record_lock(state):
        require_resolved(config_path)
        if state.exists():
            raise StorageError('booking_guard')
        if (not expected or any(not isinstance(item.get('id'), str)
                                or not re.fullmatch('[0-9a-f]{32}', item['id']) for item in expected)
                or len({item['id'] for item in expected}) != len(expected)):
            raise StorageError('records_changed')
        if linked(runs):
            raise StorageError('unsafe_path')
        for item in expected:
            try:
                current = inspect_run(runs / item['id'])
            except (ValueError, UnicodeError):
                raise StorageError('records_changed') from None
            if current != item:
                raise StorageError('records_changed')
        batch = uuid4().hex
        execute(config_path, 'move', batch, expected)
        return runs.parent / (runs.name + '.history-backups') / batch


def restore_history(config_path, destination):
    state, runs = record_paths(config_path)
    destination = Path(destination)
    root = runs.parent / (runs.name + '.history-backups')
    with record_lock(state):
        require_resolved(config_path)
        if (destination.parent != root or linked(root) or linked(destination) or linked(runs)
                or not re.fullmatch('[0-9a-f]{32}', destination.name)):
            raise StorageError('unsafe_path')
        sources = list(destination.iterdir())
        if not sources or any(linked(p) or not p.is_dir() or not re.fullmatch('[0-9a-f]{32}', p.name)
                              for p in sources):
            raise StorageError('backup_invalid')
        if any((runs / p.name).exists() or linked(runs / p.name) for p in sources):
            raise StorageError('restore_conflict')
        entries = [directory_signature(source) for source in sources]
        execute(config_path, 'restore', destination.name, entries)


def latest_backup(config_path):
    _, runs = record_paths(config_path)
    root = runs.parent / (runs.name + '.history-backups')
    if linked(root):
        raise StorageError('unsafe_path')
    excluded = incomplete_batches(config_path)
    if excluded is None:
        return None
    candidates = [p for p in root.glob('*') if p.name not in excluded and p.is_dir() and not linked(p)
                  and re.fullmatch('[0-9a-f]{32}', p.name) and any(p.iterdir())]
    return max(candidates, key=lambda p: p.stat().st_mtime_ns) if candidates else None


def backup_batches(config_path, cancel=None, report=None):
    _, runs = record_paths(config_path)
    root = runs.parent / (runs.name + '.history-backups')
    report = report if report is not None else ScanReport()
    if linked(root):
        raise StorageError('unsafe_path')
    excluded = incomplete_batches(config_path)
    if excluded is None:
        return []
    items = []
    try:
        for path in root.iterdir():
            check_cancel(cancel)
            if path.name in excluded:
                continue
            try:
                if linked(path):
                    raise RunSkipped('linked')
                if not path.is_dir() or not re.fullmatch('[0-9a-f]{32}', path.name):
                    raise RunSkipped('unsupported')
                children = list(path.iterdir())
                if not children:
                    continue  # Empty transaction directories contain no backup records.
                if any(linked(p) for p in children):
                    raise RunSkipped('linked')
                if any(not p.is_dir() or not re.fullmatch('[0-9a-f]{32}', p.name) for p in children):
                    raise RunSkipped('unsupported')
                date = datetime.fromtimestamp(path.stat().st_mtime, timezone(timedelta(hours=8)))
                items.append({'id': path.name, 'count': len(children), 'date': date.strftime('%Y-%m-%d %H:%M:%S')})
                report.accepted += 1
            except RunSkipped as error:
                report.skip(error.reason)
            except OSError as error:
                report.failure(error)
    except FileNotFoundError:
        if root.exists():
            raise
    return sorted(items, key=lambda item: (item['date'], item['id']), reverse=True)

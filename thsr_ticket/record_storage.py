"""Reversible history cleanup. Never remove the submission guard or unknown files."""
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from thsr_ticket.booking_records import record_paths
from thsr_ticket.record_lock import record_lock
from thsr_ticket.record_schema import validate_record
from thsr_ticket.storage_errors import StorageError
from thsr_ticket.storage_journal import (
    execute, require_resolved, directory_signature, incomplete_batches, pending_operations,
)


def linked(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


class ScanCancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ScanCancelled()


def inventory(config_path, cancel=None, progress=None):
    state, runs = record_paths(config_path)
    items = []
    # Any outstanding state blocks cleanup, including corrupt or unknown state.
    if linked(runs):
        raise StorageError('unsafe_path')
    if state.exists() or pending_operations(config_path):
        return items
    for index, directory in enumerate(runs.glob('*')):
        check_cancel(cancel)
        if progress and index % 20 == 0:
            progress(index)
        if not re.fullmatch('[0-9a-f]{32}', directory.name) or linked(directory) or not directory.is_dir():
            continue
        files = sorted(directory.iterdir())
        if not files or any(linked(p) or not p.is_file() or p.name not in
                            ('events.jsonl', 'result.json') for p in files):
            continue
        try:
            events = directory / 'events.jsonl'
            if not events.exists():
                continue
            last = {}
            with events.open(encoding='utf-8') as handle:
                for line in handle:
                    check_cancel(cancel)
                    last = validate_record(json.loads(line))
            if last.get('event') not in ('run_finished', 'run_stopped'):
                continue
            result = directory / 'result.json'
            if result.exists():
                validate_record(json.loads(result.read_text(encoding='utf-8')))
        except (ValueError, UnicodeError):
            continue
        digest = hashlib.sha256()
        size = 0
        for path in files:
            digest.update(path.name.encode() + b'\0')
            with path.open('rb') as handle:
                while chunk := handle.read(1024 * 1024):
                    check_cancel(cancel)
                    size += len(chunk)
                    digest.update(chunk)
        date = datetime.fromtimestamp(events.stat().st_mtime, timezone(timedelta(hours=8)))
        date = date.strftime('%Y-%m-%d %H:%M:%S')
        items.append({'id': directory.name, 'bytes': size, 'digest': digest.hexdigest(), 'date': date})
    return sorted(items, key=lambda item: item['id'])


def move_history(config_path, expected):
    state, runs = record_paths(config_path)
    with record_lock(state):
        require_resolved(config_path)
        if state.exists():
            raise StorageError('booking_guard')
        current = {item['id']: item for item in inventory(config_path)}
        if (not expected or len({item['id'] for item in expected}) != len(expected)
                or any(current.get(item['id']) != item for item in expected)):
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


def backup_batches(config_path, cancel=None):
    _, runs = record_paths(config_path)
    root = runs.parent / (runs.name + '.history-backups')
    if linked(root):
        raise StorageError('unsafe_path')
    excluded = incomplete_batches(config_path)
    if excluded is None:
        return []
    items = []
    for path in root.glob('*'):
        check_cancel(cancel)
        if path.name in excluded or linked(path) or not path.is_dir() or not re.fullmatch('[0-9a-f]{32}', path.name):
            continue
        children = list(path.iterdir())
        if not children or any(linked(p) or not p.is_dir() or not re.fullmatch('[0-9a-f]{32}', p.name)
                               for p in children):
            continue
        items.append({'id': path.name, 'count': len(children),
                      'date': datetime.fromtimestamp(path.stat().st_mtime, timezone(timedelta(hours=8)))
                      .strftime('%Y-%m-%d %H:%M:%S')})
    return sorted(items, key=lambda item: (item['date'], item['id']), reverse=True)

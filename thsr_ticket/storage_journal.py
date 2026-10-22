"""Durable local move intents and idempotent rollback after process interruption."""
import hashlib
import json
import re
from uuid import uuid4

from thsr_ticket.booking_records import record_paths
from thsr_ticket.record_lock import record_lock
from thsr_ticket.run_records import atomic_json, timestamp
from thsr_ticket.storage_errors import StorageError

IDENTIFIER = re.compile('[0-9a-f]{32}')


def linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def locations(config):
    _, runs = record_paths(config)
    backups = runs.parent / (runs.name + '.history-backups')
    journals = runs.parent / (runs.name + '.operations')
    if any(linked(path) for path in (runs, backups, journals)):
        raise StorageError('unsafe_path')
    return runs, backups, journals


def directory_signature(directory):
    if linked(directory) or not directory.is_dir():
        raise StorageError('recovery_conflict')
    files = sorted(directory.iterdir())
    if not files or any(linked(p) or not p.is_file() or p.name not in ('events.jsonl', 'result.json') for p in files):
        raise StorageError('backup_invalid')
    digest, size = hashlib.sha256(), 0
    for path in files:
        digest.update(path.name.encode() + b'\0')
        with path.open('rb') as handle:
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
    return {'id': directory.name, 'bytes': size, 'digest': digest.hexdigest()}


def read_journal(path):
    try:
        if linked(path) or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError()
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1
                or data.get('action') not in ('move', 'restore')
                or data.get('status') not in ('pending', 'complete', 'rolled_back')
                or not isinstance(data.get('batch'), str) or not IDENTIFIER.fullmatch(data['batch'])
                or not isinstance(data.get('created_at'), str)):
            raise ValueError()
        entries = data.get('entries')
        if not isinstance(entries, list) or not entries or len(entries) > 20000:
            raise ValueError()
        seen = set()
        for entry in entries:
            if (not isinstance(entry, dict) or not isinstance(entry.get('id'), str)
                    or not IDENTIFIER.fullmatch(entry['id']) or entry['id'] in seen
                    or type(entry.get('bytes')) is not int or entry['bytes'] < 0
                    or not isinstance(entry.get('digest'), str) or not re.fullmatch('[0-9a-f]{64}', entry['digest'])):
                raise ValueError()
            seen.add(entry['id'])
        return data
    except (ValueError, UnicodeError):
        raise StorageError('journal_invalid') from None


def pending_operations(config, cancel=None):
    _, _, root = locations(config)
    pending = []
    for path in root.glob('*.json'):
        if cancel is not None and cancel.is_set():
            break
        if not IDENTIFIER.fullmatch(path.stem):
            # Unknown files remain untouched and cannot be used as a recovery path.
            continue
        try:
            data = read_journal(path)
            if data['status'] != 'pending':
                continue
            pending.append({'id': path.stem, 'action': data['action'], 'count': len(data['entries']),
                            'date': data['created_at'], 'recoverable': True})
        except StorageError:
            pending.append({'id': path.stem, 'action': 'invalid', 'count': 0, 'date': '', 'recoverable': False})
    return sorted(pending, key=lambda item: (item['date'], item['id']))


def require_resolved(config):
    if pending_operations(config):
        raise StorageError('recovery_required')


def execute(config, action, batch, entries):
    """Caller holds record_lock and has checked all source/target paths."""
    runs, backups, root = locations(config)
    batch_path = backups / batch
    if linked(batch_path):
        raise StorageError('unsafe_path')
    if not IDENTIFIER.fullmatch(batch) or action not in ('move', 'restore') or len(entries) > 20000:
        raise StorageError('backup_invalid')
    source, target = (runs, batch_path) if action == 'move' else (batch_path, runs)
    target.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (uuid4().hex + '.json')
    data = {'version': 1, 'action': action, 'batch': batch, 'status': 'pending', 'created_at': timestamp(),
            'entries': [{key: item[key] for key in ('id', 'bytes', 'digest')} for item in entries]}
    atomic_json(path, data)  # fsync and replace BEFORE the first record moves.
    try:
        for item in data['entries']:
            if (target / item['id']).exists() or linked(target / item['id']):
                raise StorageError('restore_conflict')
            (source / item['id']).rename(target / item['id'])
        atomic_json(path, {**data, 'status': 'complete'})
    except Exception:
        try:
            _rollback(config, path, data)
        except Exception:
            raise StorageError('rollback_failed') from None
        raise


def _rollback(config, path, data):
    runs, backups, _ = locations(config)
    batch = backups / data['batch']
    if linked(batch):
        raise StorageError('unsafe_path')
    original, moved = (runs, batch) if data['action'] == 'move' else (batch, runs)
    actions = []
    for item in data['entries']:
        source, target = moved / item['id'], original / item['id']
        source_exists, target_exists = source.exists() or linked(source), target.exists() or linked(target)
        if source_exists == target_exists:
            raise StorageError('recovery_conflict')
        current = source if source_exists else target
        if directory_signature(current) != item:
            raise StorageError('recovery_conflict')
        if source_exists:
            actions.append((source, target))
    # Verify the entire batch before moving anything; reruns reconcile actual locations.
    original.mkdir(parents=True, exist_ok=True)
    for source, target in reversed(actions):
        if target.exists() or linked(target):
            raise StorageError('recovery_conflict')
        source.rename(target)
    atomic_json(path, {**data, 'status': 'rolled_back'})


def recover_operation(config, identifier):
    if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
        raise StorageError('journal_invalid')
    state, _ = record_paths(config)
    with record_lock(state):
        _, _, root = locations(config)
        path = root / (identifier + '.json')
        data = read_journal(path)
        if data['status'] == 'rolled_back':
            return  # A repeated recovery confirmation is harmless.
        if data['status'] != 'pending':
            raise StorageError('records_changed')
        _rollback(config, path, data)


def incomplete_batches(config):
    """Exclude interrupted batches from the ordinary restore list."""
    _, _, root = locations(config)
    result = set()
    for item in pending_operations(config):
        if not item['recoverable']:
            return None  # Unknown intent: don't offer normal mutations.
        result.add(read_journal(root / (item['id'] + '.json'))['batch'])
    return result

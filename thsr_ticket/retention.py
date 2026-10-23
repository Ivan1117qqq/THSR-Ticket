"""Preview and delete only old, completed query logs; keep booking evidence and an audit."""
import re
from datetime import datetime, timedelta
from uuid import uuid4

from thsr_ticket.automation import TAIPEI
from thsr_ticket.backup import safe_path
from thsr_ticket.booking_records import record_paths
from thsr_ticket.record_lock import record_lock
from thsr_ticket.record_storage import inspect_run, RunSkipped
from thsr_ticket.run_records import atomic_json, timestamp
from thsr_ticket.scan_report import check_cancel
from thsr_ticket.storage_errors import StorageError
from thsr_ticket.storage_journal import require_resolved
from thsr_ticket.config_store import require_complete_restore


def preview_cleanup(config, days=90, cancel=None, now=None):
    if type(days) is not int or not 1 <= days <= 3650:
        raise ValueError('保留天數須為 1–3650。')
    config = safe_path(config)
    require_complete_restore(config)
    state, runs = record_paths(config)
    safe_path(state)
    safe_path(runs)
    cutoff = ((now or datetime.now(TAIPEI)) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    items, protected, failures = [], 0, 0
    with record_lock(state):
        require_resolved(config)
        if state.exists():
            raise StorageError('booking_guard')
        roots = [runs]
        backups = safe_path(runs.parent / (runs.name + '.history-backups'))
        if backups.exists():
            for batch in backups.iterdir():
                check_cancel(cancel)
                if re.fullmatch('[0-9a-f]{32}', batch.name) and batch.is_dir():
                    roots.append(safe_path(batch))
                else:
                    protected += 1
        for root in roots:
            check_cancel(cancel)
            if not root.exists():
                continue
            for directory in root.iterdir():
                check_cancel(cancel)
                if len(items) >= 20000:
                    raise StorageError('backup_limit')
                try:
                    if not re.fullmatch('[0-9a-f]{32}', directory.name):
                        protected += 1
                        continue
                    safe_path(directory)
                    # Any result is booking evidence, regardless of its local status or age.
                    if (directory / 'result.json').exists():
                        protected += 1
                        continue
                    item = inspect_run(directory, cancel, query_only=True)
                    if item['date'] >= cutoff:
                        protected += 1
                        continue
                    item['relative'] = directory.relative_to(config.parent).as_posix()
                    items.append(item)
                except (ValueError, OSError, RunSkipped):
                    failures += 1
    return {'config': config, 'days': days, 'cutoff': cutoff, 'items': items,
            'bytes': sum(item['bytes'] for item in items), 'protected': protected, 'skipped': failures}


def apply_cleanup(plan):
    config = safe_path(plan['config'])
    require_complete_restore(config)
    state, runs = record_paths(config)
    with record_lock(state):
        require_resolved(config)
        if state.exists():
            raise StorageError('booking_guard')
        checked = []
        for expected in plan['items']:
            path = safe_path(config.parent / expected['relative'])
            allowed = path.parent == runs or (path.parent.parent == runs.parent / (runs.name + '.history-backups')
                                              and re.fullmatch('[0-9a-f]{32}', path.parent.name))
            if not allowed or (path / 'result.json').exists():
                raise StorageError('records_changed')
            try:
                current = inspect_run(path, query_only=True)
            except (ValueError, UnicodeError):
                raise StorageError('records_changed') from None
            if current != {key: value for key, value in expected.items() if key != 'relative'}:
                raise StorageError('records_changed')
            checked.append(path)
        if not checked or len(set(checked)) != len(checked):
            raise StorageError('records_changed')
        audit_dir = safe_path(runs / 'cleanup')
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_path = audit_dir / (uuid4().hex + '.json')
        audit = {'_record_version': 1, 'status': 'pending', 'created_at': timestamp(), 'days': plan['days'],
                 'cutoff': plan['cutoff'], 'requested': len(checked), 'deleted': 0, 'bytes_deleted': 0,
                 'entries': [{key: item[key] for key in ('relative', 'date', 'bytes', 'digest')}
                             for item in plan['items']]}
        atomic_json(audit_path, audit)  # If evidence cannot be saved, delete nothing.
        try:
            for directory, expected in zip(checked, plan['items']):
                safe_path(directory)
                if (directory / 'result.json').exists():
                    raise StorageError('records_changed')
                # inspect_run accepted only events.jsonl here. Never recursively delete a tree.
                files = list(directory.iterdir())
                if len(files) != 1 or files[0].name != 'events.jsonl':
                    raise StorageError('records_changed')
                safe_path(files[0]).unlink()
                audit['deleted'] += 1
                audit['bytes_deleted'] += expected['bytes']
                directory.rmdir()
                atomic_json(audit_path, audit)
            audit['status'] = 'completed'
        except Exception:
            audit['status'] = 'partial'
            atomic_json(audit_path, audit)
            raise StorageError('cleanup_partial') from None
        atomic_json(audit_path, audit)
        return audit

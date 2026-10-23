"""Bounded, byte-preserving backups; restore only to a new directory with a guard."""
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from unicodedata import normalize

from thsr_ticket.booking_records import record_paths
from thsr_ticket.config_store import is_protected, RESTORE_MARKER
from thsr_ticket.record_lock import record_lock
from thsr_ticket.run_records import timestamp, atomic_json
from thsr_ticket.scan_report import check_cancel
from thsr_ticket.storage_errors import StorageError
from thsr_ticket.version import VERSION

MAX_FILES = 20000
MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_MANIFEST = 8 * 1024 * 1024
CHUNK = 1024 * 1024
ROOT_FILES = {'config.json', 'state.json', 'task.json'}
TREES = {'runs', 'history-backups', 'operations', 'config-backups'}
RESERVED = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{prefix}{n}' for prefix in ('COM', 'LPT') for n in range(1, 10)}


def safe_path(path):
    """Check before resolving, including ancestor junctions on Windows."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise StorageError('unsafe_path')
    return path


def member_name(name):
    if not isinstance(name, str) or len(name.encode('utf-8')) > 600:
        raise StorageError('backup_invalid')
    parts = name.split('/')
    for part in parts:
        if (not part or part in ('.', '..') or len(part) > 128 or part[-1] in '. '
                or any(ord(char) < 32 or char in '<>:"\\|?*' for char in part)
                or part.split('.')[0].upper() in RESERVED):
            raise StorageError('backup_invalid')
    if (len(parts) > 12 or (len(parts) == 1 and name not in ROOT_FILES)
            or (len(parts) > 1 and parts[0] not in TREES)
            or PurePosixPath(name).suffix.lower() not in ('.json', '.jsonl')):
        raise StorageError('backup_invalid')
    return normalize('NFC', name).casefold()


def sources(config):
    config = safe_path(config)
    state, runs = record_paths(config)
    return {'config.json': config, 'state.json': state, 'task.json': config.with_suffix('.task.json'),
            'runs': runs, 'history-backups': runs.parent / (runs.name + '.history-backups'),
            'operations': runs.parent / (runs.name + '.operations'),
            'config-backups': config.parent / (config.name + '.config-backups')}


def signature(path):
    value = path.stat()
    if not stat.S_ISREG(value.st_mode):
        raise StorageError('unsafe_path')
    return value.st_size, value.st_mtime_ns, value.st_ino, value.st_dev


def inventory(config, cancel=None):
    roots = sources(config)
    result, folded = {}, set()

    def add(name, path):
        check_cancel(cancel)
        key = member_name(name)
        if key in folded:
            raise StorageError('backup_invalid')
        folded.add(key)
        safe_path(path)
        token = signature(path)
        if token[0] > MAX_FILE or len(result) >= MAX_FILES:
            raise StorageError('backup_limit')
        result[name] = {'path': path, 'token': token}

    for name, path in roots.items():
        check_cancel(cancel)
        safe_path(path)
        if not path.exists():
            if name == 'config.json':
                raise StorageError('backup_config_missing')
            continue
        if name in ROOT_FILES:
            add(name, path)
        else:
            if not path.is_dir():
                raise StorageError('unsafe_path')
            stack = [path]
            while stack:
                directory = stack.pop()
                check_cancel(cancel)
                for item in directory.iterdir():
                    check_cancel(cancel)
                    safe_path(item)
                    if item.is_dir():
                        stack.append(item)
                    else:
                        add(name + '/' + item.relative_to(path).as_posix(), item)
    if sum(item['token'][0] for item in result.values()) > MAX_TOTAL:
        raise StorageError('backup_limit')
    return result


def transfer(source, destination=None, limit=MAX_FILE, cancel=None):
    digest, size = hashlib.sha256(), 0
    while chunk := source.read(CHUNK):
        check_cancel(cancel)
        size += len(chunk)
        if size > limit:
            raise StorageError('backup_limit')
        digest.update(chunk)
        if destination is not None:
            destination.write(chunk)
    return size, digest.hexdigest()


def describe(manifest, config_bytes):
    counts = {name: 0 for name in ('configuration', 'state', 'task', *sorted(TREES))}
    for entry in manifest['files']:
        role = entry['name'].split('/')[0]
        counts[{'config.json': 'configuration', 'state.json': 'state', 'task.json': 'task'}.get(role, role)] += 1
    protection = 'unknown'
    try:
        config = json.loads(config_bytes)
        if isinstance(config, dict):
            protection = 'windows-dpapi' if is_protected(config) else 'plain'
    except (ValueError, UnicodeError, RecursionError):
        pass
    return {'files': len(manifest['files']), 'bytes': sum(item['bytes'] for item in manifest['files']),
            'groups': counts, 'has_state': bool(counts['state']), 'protection': protection,
            'app_version': manifest['app_version'], 'created_at': manifest['created_at']}


def preview_source(config, cancel=None):
    config = safe_path(config)
    if not config.exists():
        raise StorageError('backup_config_missing')
    if (config.parent / RESTORE_MARKER).exists():
        raise StorageError('backup_restore_pending')
    safe_path(config.with_suffix('.state.operation.lock'))
    with record_lock(config.with_suffix('.state.json')):
        items = inventory(config, cancel)
        entries = []
        for name, item in sorted(items.items()):
            with item['path'].open('rb') as handle:
                size, digest = transfer(handle, cancel=cancel)
            if signature(item['path']) != item['token'] or size != item['token'][0]:
                raise StorageError('backup_source_changed')
            entries.append({'name': name, 'bytes': size, 'sha256': digest, 'mtime_ns': item['token'][1]})
        if inventory(config, cancel) != items:
            raise StorageError('backup_source_changed')
        manifest = {'format': 'travel-desk-backup', 'version': 1, 'app_version': VERSION,
                    'created_at': timestamp(), 'files': entries}
        raw = items['config.json']['path'].read_bytes() if items['config.json']['token'][0] <= MAX_MANIFEST else b''
        return {'config': config, 'items': items, 'manifest': manifest, 'summary': describe(manifest, raw)}


def export_backup(plan, target):
    target = safe_path(target)
    if not target.name.endswith('.thsr-backup.zip'):
        raise StorageError('backup_extension')
    for role, path in sources(plan['config']).items():
        if role in TREES and target.is_relative_to(path):
            raise StorageError('unsafe_path')
    if target.exists():
        raise StorageError('backup_destination_exists')
    temporary = None
    safe_path(plan['config'].with_suffix('.state.operation.lock'))
    manifest_bytes = json.dumps(plan['manifest'], ensure_ascii=False).encode('utf-8')
    if len(manifest_bytes) > MAX_MANIFEST:
        raise StorageError('backup_limit')
    with record_lock(plan['config'].with_suffix('.state.json')):
        if inventory(plan['config']) != plan['items']:
            raise StorageError('backup_source_changed')
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.thsr-backup-', suffix='.tmp',
                                             delete=False) as out:
                temporary = Path(out.name)
                with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    for entry in plan['manifest']['files']:
                        path = plan['items'][entry['name']]['path']
                        with path.open('rb') as source, archive.open(entry['name'], 'w') as destination:
                            size, digest = transfer(source, destination)
                        if (size, digest) != (entry['bytes'], entry['sha256']):
                            raise StorageError('backup_source_changed')
                    archive.writestr('manifest.json', manifest_bytes)
                out.flush()
                os.fsync(out.fileno())
            if inventory(plan['config']) != plan['items']:
                raise StorageError('backup_source_changed')
            # Exclusive creation also handles a destination appearing after preview.
            created = False
            try:
                with target.open('xb') as destination:
                    created = True
                    with temporary.open('rb') as source:
                        transfer(source, destination, limit=MAX_TOTAL + MAX_MANIFEST + MAX_FILES * 2048)
                    destination.flush()
                    os.fsync(destination.fileno())
            except FileExistsError:
                raise StorageError('backup_destination_exists') from None
            except BaseException:
                if created:
                    target.unlink(missing_ok=True)
                raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return target


def validate_manifest(archive):
    infos = archive.infolist()
    if len(infos) > MAX_FILES + 1 or len({item.filename for item in infos}) != len(infos):
        raise StorageError('backup_invalid')
    index = {item.filename: item for item in infos}
    metadata = index.get('manifest.json')
    if metadata is None or metadata.file_size > MAX_MANIFEST:
        raise StorageError('backup_invalid')
    try:
        manifest = json.loads(archive.read(metadata))
    except (ValueError, UnicodeError, RecursionError):
        raise StorageError('backup_invalid') from None
    if (not isinstance(manifest, dict) or manifest.get('format') != 'travel-desk-backup'
            or type(manifest.get('version')) is not int or manifest['version'] != 1
            or not isinstance(manifest.get('app_version'), str)
            or not re.fullmatch(r'\d{1,5}\.\d{1,5}\.\d{1,5}', manifest['app_version'])
            or not isinstance(manifest.get('created_at'), str)
            or not re.fullmatch(r'\d{4}-\d\d-\d\dT[0-9:.+\-]{8,32}', manifest['created_at'])
            or not isinstance(manifest.get('files'), list) or not 1 <= len(manifest['files']) <= MAX_FILES):
        raise StorageError('backup_invalid')
    names, folded, total = set(), set(), 0
    for entry in manifest['files']:
        if not isinstance(entry, dict) or set(entry) != {'name', 'bytes', 'sha256', 'mtime_ns'}:
            raise StorageError('backup_invalid')
        key = member_name(entry['name'])
        if (key in folded or entry['name'] not in index or type(entry['bytes']) is not int
                or not 0 <= entry['bytes'] <= MAX_FILE or not isinstance(entry['sha256'], str)
                or not re.fullmatch('[0-9a-f]{64}', entry['sha256'])
                or type(entry['mtime_ns']) is not int or not -(2 ** 63) <= entry['mtime_ns'] < 2 ** 63):
            raise StorageError('backup_invalid')
        info = index[entry['name']]
        mode = stat.S_IFMT(info.external_attr >> 16)
        if (info.file_size != entry['bytes'] or mode not in (0, stat.S_IFREG)
                or info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
            raise StorageError('backup_invalid')
        folded.add(key)
        names.add(entry['name'])
        total += entry['bytes']
    if total > MAX_TOTAL or 'config.json' not in names or names | {'manifest.json'} != set(index):
        raise StorageError('backup_invalid')
    if any('/'.join(name.split('/')[:n]) in folded for name in folded for n in range(1, len(name.split('/')))):
        raise StorageError('backup_invalid')
    return manifest


def inspect_open(raw, cancel=None):
    raw.seek(0)
    _, fingerprint = transfer(raw, limit=MAX_TOTAL + MAX_MANIFEST + MAX_FILES * 2048, cancel=cancel)
    raw.seek(0)
    try:
        with zipfile.ZipFile(raw) as archive:
            manifest = validate_manifest(archive)
            config_bytes = b''
            for entry in manifest['files']:
                with archive.open(entry['name']) as source:
                    size, digest = transfer(source, limit=entry['bytes'], cancel=cancel)
                if (size, digest) != (entry['bytes'], entry['sha256']):
                    raise StorageError('backup_invalid')
                if entry['name'] == 'config.json' and size <= MAX_MANIFEST:
                    config_bytes = archive.read(entry['name'])
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError):
        raise StorageError('backup_invalid') from None
    return manifest, fingerprint, describe(manifest, config_bytes)


def destination_path(target):
    target = safe_path(target)
    if target.exists():
        raise StorageError('backup_destination_exists')
    if not target.parent.is_dir():
        raise StorageError('unsafe_path')
    return target


def preview_archive(path, target=None, cancel=None):
    path = safe_path(path)
    before = signature(path)
    if before[0] > MAX_TOTAL + MAX_MANIFEST + MAX_FILES * 2048:
        raise StorageError('backup_limit')
    with path.open('rb') as raw:
        manifest, fingerprint, summary = inspect_open(raw, cancel)
    if signature(path) != before:
        raise StorageError('backup_source_changed')
    target = destination_path(target) if target is not None else None
    return {'archive': path, 'fingerprint': fingerprint, 'manifest': manifest, 'summary': summary, 'target': target}


def restored_name(name):
    replacements = {'config.json': 'booking.local.json', 'state.json': 'booking.local.state.json',
                    'task.json': 'booking.local.task.json', 'runs': 'booking.local.runs',
                    'history-backups': 'booking.local.runs.history-backups',
                    'operations': 'booking.local.runs.operations',
                    'config-backups': 'booking.local.json.config-backups'}
    first, *rest = name.split('/')
    return Path(replacements[first], *rest)


def restore_backup(plan):
    target = destination_path(plan['target'])
    archive_path = safe_path(plan['archive'])
    with archive_path.open('rb') as raw:
        manifest, fingerprint, _ = inspect_open(raw)
        if fingerprint != plan['fingerprint'] or manifest != plan['manifest']:
            raise StorageError('backup_source_changed')
        target.mkdir()  # Refuse even an empty directory; do not merge or overwrite.
        marker = target / RESTORE_MARKER
        atomic_json(marker, {'version': 1, 'status': 'incomplete'})
        by_name = {entry['name']: entry for entry in manifest['files']}
        if 'state.json' not in by_name:
            atomic_json(target / 'booking.local.state.json', {
                '_record_version': 1, 'status': 'submission_pending', 'restored_without_state': True,
                'saved_at': timestamp(),
            })
        order = sorted(by_name, key=lambda name: (name == 'config.json', name != 'state.json', name))
        with zipfile.ZipFile(raw) as archive:
            for name in order:
                entry = by_name[name]
                output = target / restored_name(name)
                output.parent.mkdir(parents=True, exist_ok=True)
                safe_path(output)
                with archive.open(name) as source, output.open('xb') as destination:
                    size, digest = transfer(source, destination, limit=entry['bytes'])
                    destination.flush()
                    os.fsync(destination.fileno())
                if (size, digest) != (entry['bytes'], entry['sha256']):
                    raise StorageError('backup_invalid')
                os.utime(output, ns=(entry['mtime_ns'], entry['mtime_ns']))
        raw.seek(0)
        if transfer(raw, limit=MAX_TOTAL + MAX_MANIFEST + MAX_FILES * 2048)[1] != fingerprint:
            raise StorageError('backup_source_changed')
        marker.unlink()  # Config readers reject the directory until everything is written and checked.
    return target / 'booking.local.json'

"""Reversible history cleanup. Never remove the submission guard or unknown files."""
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from thsr_ticket.booking_records import record_paths
from thsr_ticket.record_lock import record_lock
from thsr_ticket.record_schema import validate_record


def linked(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def inventory(config_path):
    state, runs = record_paths(config_path)
    items = []
    # Any outstanding state blocks cleanup, including corrupt or unknown state.
    if state.exists() or linked(runs):
        return items
    for directory in sorted(runs.glob('*')):
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
            entries = [validate_record(json.loads(line)) for line in events.read_text(encoding='utf-8').splitlines()]
            if not entries or entries[-1].get('event') not in ('run_finished', 'run_stopped'):
                continue
            result = directory / 'result.json'
            if result.exists():
                validate_record(json.loads(result.read_text(encoding='utf-8')))
        except (ValueError, UnicodeError):
            continue
        digest = hashlib.sha256()
        size = 0
        for path in files:
            content = path.read_bytes()
            size += len(content)
            digest.update(path.name.encode() + b'\0' + content)
        items.append({'id': directory.name, 'bytes': size, 'digest': digest.hexdigest()})
    return items


def move_history(config_path, expected):
    state, runs = record_paths(config_path)
    with record_lock(state):
        if not expected or inventory(config_path) != expected:
            raise ValueError('紀錄已變更或仍有待處理訂位，請重新預覽。')
        destination = runs.parent / (runs.name + '.history-backups') / uuid4().hex
        if linked(destination.parent):
            raise ValueError('備份目錄不可為連結。')
        destination.mkdir(parents=True, exist_ok=False)
        moved = []
        try:
            for item in expected:
                source = runs / item['id']
                source.rename(destination / source.name)
                moved.append(source.name)
        except OSError:
            for name in reversed(moved):
                (destination / name).rename(runs / name)
            raise
        return destination


def restore_history(config_path, destination):
    state, runs = record_paths(config_path)
    destination = Path(destination)
    root = runs.parent / (runs.name + '.history-backups')
    with record_lock(state):
        if (destination.parent != root or linked(root) or linked(destination) or linked(runs)
                or not re.fullmatch('[0-9a-f]{32}', destination.name)):
            raise ValueError('無效的備份位置。')
        sources = list(destination.iterdir())
        if any(linked(p) or not p.is_dir() or not re.fullmatch('[0-9a-f]{32}', p.name)
               or (runs / p.name).exists() for p in sources):
            raise ValueError('紀錄已存在或備份格式異常，未還原。')
        runs.mkdir(parents=True, exist_ok=True)
        moved = []
        try:
            for source in sources:
                source.rename(runs / source.name)
                moved.append(source.name)
        except OSError:
            for name in reversed(moved):
                (runs / name).rename(destination / name)
            raise
        destination.rmdir()


def latest_backup(config_path):
    _, runs = record_paths(config_path)
    root = runs.parent / (runs.name + '.history-backups')
    if linked(root):
        raise ValueError('備份目錄不可為連結。')
    candidates = [p for p in root.glob('*') if p.is_dir() and not linked(p)
                  and re.fullmatch('[0-9a-f]{32}', p.name) and any(p.iterdir())]
    return max(candidates, key=lambda p: p.stat().st_mtime_ns) if candidates else None

"""Local run records with explicit fields; never serialize requests or config objects."""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


def timestamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='milliseconds')


def atomic_json(path, data):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.record-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


class RunRecords:
    def __init__(self, state_path):
        state_path = Path(state_path)
        base = state_path.name.removesuffix('.state.json')
        self.run_id = uuid4().hex
        self.directory = state_path.parent / f'{base}.runs' / self.run_id
        self.events_path = self.directory / 'events.jsonl'
        self.result_path = self.directory / 'result.json'
        self.disabled = False

    def event(self, event, **fields):
        if self.disabled:
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with self.events_path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps({'time': timestamp(), 'event': event, **fields}, ensure_ascii=False) + '\n')
        except OSError:
            self.disabled = True
            print('執行紀錄無法寫入；本次後續紀錄將略過，不會因此重送訂位。')

    def save_result(self, tickets, outbound_date):
        self.directory.mkdir(parents=True, exist_ok=True)
        atomic_json(self.result_path, {
            'saved_at': timestamp(), 'status': 'booked', 'payment_status': 'unpaid',
            'requested_outbound_date': outbound_date,
            'tickets': [ticket._asdict() for ticket in tickets],
        })

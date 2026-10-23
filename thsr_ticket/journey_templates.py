"""Named, non-secret journey presets; dates and booking identities never enter this store."""
import json
import math
import re
from pathlib import Path
from uuid import uuid4

from thsr_ticket.application import STATIONS
from thsr_ticket.automation import clock_time
from thsr_ticket.run_records import atomic_json

COUNTS = ('adult_tickets', 'child_tickets', 'disabled_tickets', 'elder_tickets', 'college_tickets')
FIELDS = ('start_station', 'dest_station', 'class_type', 'earliest_departure', 'latest_departure',
          'train_ids', *COUNTS, 'interval_seconds', 'max_attempts', 'ocr_model',
          'network_failure_limit', 'max_network_delay_seconds')


def template_values(form):
    defaults = {'network_failure_limit': '3', 'max_network_delay_seconds': '30'}
    result = {key: str(form[key] if key in form else defaults[key]).strip() for key in FIELDS}
    if any(len(value) > (600 if key == 'train_ids' else 80) for key, value in result.items()):
        raise ValueError('範本欄位過長，請縮短後再試。')
    if (result['start_station'] not in STATIONS or result['dest_station'] not in STATIONS
            or result['start_station'] == result['dest_station'] or result['class_type'] not in ('標準', '商務')
            or result['ocr_model'] not in ('standard', 'beta')):
        raise ValueError('請檢查起訖站、車廂及 OCR 模型。')
    for field in ('earliest_departure', 'latest_departure'):
        clock_time(result[field])
    if result['earliest_departure'] > result['latest_departure']:
        raise ValueError('最晚出發不可早於最早出發。')
    for field, low, high in [*((key, 0, 10) for key in COUNTS),
                             ('max_attempts', 1, 10000), ('network_failure_limit', 1, 100)]:
        if not re.fullmatch(r'\d{1,5}', result[field]) or not low <= int(result[field]) <= high:
            raise ValueError('請檢查票數與查詢輪數。')
        result[field] = str(int(result[field]))
    if not 1 <= sum(int(result[key]) for key in COUNTS) <= 10:
        raise ValueError('票數合計須為 1–10 張。')
    for field, low, high in [('interval_seconds', 0, None), ('max_network_delay_seconds', 2, 3600)]:
        value = float(result[field])
        if not math.isfinite(value) or (value <= 0 if low == 0 else value < low) or (high and value > high):
            raise ValueError('請檢查查詢間隔與退避秒數。')
    ids = [part.strip() for part in result['train_ids'].replace('，', ',').split(',')] if result['train_ids'] else []
    if (len(ids) > 100 or any(not re.fullmatch(r'\d{1,4}', part) or int(part) == 0 for part in ids)
            or len({int(part) for part in ids}) != len(ids)):
        raise ValueError('偏好車次須為不重複的正整數，以逗號分隔。')
    result['train_ids'] = ', '.join(str(int(part)) for part in ids)
    return result


def template_name(value):
    value = value.strip()
    if not 1 <= len(value) <= 40 or any(ord(char) < 32 for char in value):
        raise ValueError('範本名稱須為 1–40 字。')
    return value


class TemplateStore:
    LIMIT = 50

    def __init__(self, directory):
        self.path = Path(directory) / 'journey-templates.json'

    def read(self):
        if self.path.is_symlink():
            raise ValueError('範本檔案不可為連結，原檔保留。')
        if not self.path.exists():
            return []
        if self.path.stat().st_size > 256 * 1024:
            raise ValueError('範本檔案無法讀取，原檔保留。')
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or set(data) != {'version', 'items'}
                or type(data['version']) is not int or data['version'] != 1):
            raise ValueError('不支援的範本版本，原檔保留。')
        items = data['items']
        if not isinstance(items, list) or len(items) > self.LIMIT:
            raise ValueError('範本數量或格式無效。')
        seen, names = set(), set()
        for item in items:
            if (not isinstance(item, dict) or set(item) != {'id', 'name', 'values'}
                    or not isinstance(item['id'], str) or not re.fullmatch('[0-9a-f]{32}', item['id'])
                    or item['id'] in seen or not isinstance(item['name'], str)
                    or not isinstance(item['values'], dict) or set(item['values']) != set(FIELDS)):
                raise ValueError('範本格式無效，原檔保留。')
            name = template_name(item['name'])
            if name.casefold() in names or template_values(item['values']) != item['values']:
                raise ValueError('範本名稱重複或內容無效。')
            seen.add(item['id'])
            names.add(name.casefold())
        return items

    def _write(self, items):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self.path, {'version': 1, 'items': items})

    def save(self, name, form, identifier=''):
        name, values = template_name(name), template_values(form)
        items = self.read()
        if any(item['name'].casefold() == name.casefold() and item['id'] != identifier for item in items):
            raise ValueError('已有同名範本，請換個名稱。')
        target = next((item for item in items if item['id'] == identifier), None)
        if identifier and target is None:
            raise ValueError('範本已變更，請重新開啟。')
        if target is None:
            if len(items) >= self.LIMIT:
                raise ValueError('最多保存 50 個範本。')
            target = {'id': uuid4().hex}
            items.append(target)
        target.update(name=name, values=values)
        self._write(items)
        return target['id']

    def delete(self, identifier):
        items = self.read()
        remaining = [item for item in items if item['id'] != identifier]
        if len(remaining) == len(items):
            raise ValueError('範本已不存在。')
        self._write(remaining)

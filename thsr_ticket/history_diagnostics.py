"""Bounded, read-only historical diagnostics with allowlisted output."""
import json
import re
from collections import deque
from datetime import datetime, timedelta, timezone

from thsr_ticket.booking_records import record_paths
from thsr_ticket.diagnostics import safe_event, PHASES
from thsr_ticket.record_schema import validate_record
from thsr_ticket.scan_report import ScanReport, check_cancel, children
from thsr_ticket.storage_errors import StorageError
from thsr_ticket.version import VERSION

MAX_RUNS = 200
MAX_BYTES = 4 * 1024 * 1024
MAX_LINE = 64 * 1024
IDENTIFIER = re.compile('[0-9a-f]{32}')
TAIPEI = timezone(timedelta(hours=8))
PHASE_LABELS = {'prepare': '準備', 'schedule': '等待排程', 'homepage': '連線網站', 'captcha_image': '取得驗證碼',
                'ocr': '辨識驗證碼', 'query': '查詢車次', 'select_train': '選擇車次',
                'submit_ticket': '送出訂位', 'parse_result': '確認結果', 'preflight': '啟動檢查',
                'browser_start': '啟動瀏覽器', 'ocr_load': '準備辨識元件'}
DETAILS = {
    'success': ('任務完成', '若為訂位模式，請到「我的訂位」查看保存結果；付款與取消狀態以官網為準。'),
    'query_success': ('查票完成', '這次是只查票模式，沒有送出訂位；座位資訊可能已改變。'),
    'attempt_limit': ('已達查詢上限', '可檢查時段、車次與查詢輪數後，手動啟動新任務。'),
    'stopped': ('任務已停止', '停止不代表取消既有訂位；若曾送出訂位，請核對官網。'),
    'network': ('連線中斷', '請確認網路與官網狀態；若曾送出訂位，先核對結果再操作。'),
    'website_rejected': ('網站拒絕操作', '請核對官網公告與訂位條件，不要直接提高重試頻率。'),
    'ocr_unavailable': ('辨識元件無法使用', '請到設定頁檢查環境與辨識套件。'),
    'browser_start': ('瀏覽器無法啟動', '請確認已安裝 Chrome，並到設定頁檢查環境。'),
    'preflight': ('啟動檢查未通過', '請檢查設定及目前訂位狀態；原有防重送紀錄仍需先核對。'),
    'booking_unconfirmed': ('訂位結果需要核對', '請保留本機紀錄並核對官網；診斷紀錄不能作為再次送出訂位的依據。'),
    'incomplete': ('執行紀錄未完整結束', '可能是中斷、仍在執行或紀錄不完整；先確認目前任務與官網狀態。'),
    'failed': ('任務未完成', '請檢查失敗階段與設定；涉及送出訂位時，先核對官網結果。'),
}


def linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def metadata(value):
    result = {'app_version': 'unknown', 'python_version': 'unknown', 'platform': 'unknown', 'query_only': None}
    if not isinstance(value, dict) or value.get('event') != 'run_started':
        return result
    for field in ('app_version', 'python_version'):
        item = value.get(field)
        if isinstance(item, str) and re.fullmatch(r'\d{1,5}\.\d{1,5}\.\d{1,5}', item):
            result[field] = item
    if value.get('platform') in ('Windows', 'Linux', 'Darwin'):
        result['platform'] = value['platform']
    if type(value.get('query_only')) is bool:
        result['query_only'] = value['query_only']
    return result


def read_diagnostic(path, cancel=None):
    if linked(path) or linked(path.parent):
        raise StorageError('unsafe_path')
    before = path.stat()
    events = deque(maxlen=200)
    malformed = 0
    provenance = metadata(None)
    terminal = None
    phase = 'prepare'
    uncertain = False
    with path.open('rb') as handle:
        head = handle.readline(MAX_LINE + 1)
        if len(head) <= MAX_LINE:
            try:
                provenance = metadata(validate_record(json.loads(head)))
            except (ValueError, UnicodeError, RecursionError):
                pass
        consumed = 0
        if before.st_size > MAX_BYTES:
            handle.seek(before.st_size - MAX_BYTES)
            # Discard a partial first line without allocating an unbounded string.
            while consumed < MAX_BYTES:
                check_cancel(cancel)
                fragment = handle.readline(min(MAX_LINE + 1, MAX_BYTES - consumed))
                if not fragment:
                    break
                consumed += len(fragment)
                if fragment.endswith(b'\n'):
                    break
        else:
            handle.seek(0)
        while consumed < MAX_BYTES:
            check_cancel(cancel)
            line = handle.readline(min(MAX_LINE + 1, MAX_BYTES - consumed))
            if not line:
                break
            consumed += len(line)
            if len(line) > MAX_LINE:
                malformed += 1
                while consumed < MAX_BYTES and not line.endswith(b'\n'):
                    check_cancel(cancel)
                    line = handle.readline(min(MAX_LINE + 1, MAX_BYTES - consumed))
                    consumed += len(line)
                    if not line:
                        break
                continue
            try:
                value = validate_record(json.loads(line))
                clean = safe_event(value)
            except (ValueError, UnicodeError, RecursionError):
                malformed += 1
                continue
            if not clean:
                continue
            events.append(clean)
            phase = clean.get('phase', phase)
            if clean['event'] in ('run_finished', 'run_stopped', 'task_completed'):
                terminal = clean
            if clean['event'] in ('result_save_failed', 'state_update_failed'):
                uncertain = True
    after = path.stat()
    changed = (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
    code = 'incomplete'
    if terminal:
        reason = terminal.get('reason')
        if terminal['event'] == 'task_completed':
            code = {'success': 'query_success' if provenance['query_only'] is True else 'success',
                    'stopped': 'stopped', 'attempt_limit': 'attempt_limit', 'network': 'network',
                    'website_rejected': 'website_rejected', 'browser_start': 'browser_start',
                    'ocr_load': 'ocr_unavailable', 'preflight': 'preflight',
                    'booking_unconfirmed': 'booking_unconfirmed'}.get(terminal.get('outcome'), 'failed')
        elif terminal['event'] == 'run_finished':
            code = ('query_success' if provenance['query_only'] is True else 'success') \
                if terminal.get('outcome') == 'success' else (
                    'attempt_limit' if terminal.get('outcome') == 'attempt_limit' else 'failed')
        else:
            code = {'network_timeout': 'network', 'network_error': 'network', 'http_error': 'network',
                    'website_rejected': 'website_rejected', 'ocr_unavailable': 'ocr_unavailable',
                    'interrupted': 'stopped', 'booking_unconfirmed': 'booking_unconfirmed'}.get(reason, 'failed')
    submitted_failure = phase in ('submit_ticket', 'parse_result') and code not in ('success', 'query_success')
    if provenance['query_only'] is not True and (uncertain or submitted_failure):
        code = 'booking_unconfirmed'
    if changed:
        code = 'incomplete'
    title, guidance = DETAILS[code]
    warnings = {'malformed_lines': malformed, 'tail_only': before.st_size > MAX_BYTES, 'changed_during_read': changed}
    snapshot = {'schema_version': 1, 'scope': 'historical_run; latest 200 allowlisted events',
                'viewer_app_version': VERSION, 'recorded_environment': provenance,
                'outcome': code, 'phase': phase if phase in PHASES else 'prepare',
                'warnings': warnings, 'events': list(events)}
    return {'title': title, 'guidance': guidance, 'code': code, 'phase': PHASE_LABELS.get(phase, '未記錄'),
            'date': datetime.fromtimestamp(before.st_mtime, TAIPEI).strftime('%Y-%m-%d %H:%M:%S'),
            'snapshot': snapshot, 'recorded_version': provenance['app_version'],
            'partial': bool(malformed or warnings['tail_only'] or changed)}


def scan_history(config, cancel=None):
    _, runs = record_paths(config)
    backups = runs.parent / (runs.name + '.history-backups')
    if linked(runs) or linked(backups):
        raise StorageError('unsafe_path')
    report = ScanReport()
    candidates = []

    def collect(root, prefix):
        for directory in children(root):
            check_cancel(cancel)
            if not IDENTIFIER.fullmatch(directory.name):
                continue
            try:
                if linked(directory):
                    report.skip('linked')
                    continue
                path = directory / 'events.jsonl'
                if linked(path):
                    report.skip('linked')
                    continue
                stat = path.stat()
                candidates.append((stat.st_mtime_ns, prefix + directory.name, path))
            except FileNotFoundError:
                continue
            except OSError as error:
                report.failure(error)

    collect(runs, 'runs/')
    for batch in children(backups):
        check_cancel(cancel)
        if not IDENTIFIER.fullmatch(batch.name):
            continue
        try:
            if linked(batch):
                report.skip('linked')
                continue
            collect(batch, 'backups/' + batch.name + '/')
        except OSError as error:
            report.failure(error)
    rows, snapshots = [], {}
    for _, identifier, path in sorted(candidates, reverse=True)[:MAX_RUNS]:
        check_cancel(cancel)
        try:
            value = read_diagnostic(path, cancel)
        except OSError as error:
            report.failure(error)
        except StorageError:
            report.skip('linked')
        else:
            snapshots[identifier] = value.pop('snapshot')
            rows.append({'id': identifier, **value})
            report.accepted += 1
    return rows, snapshots, {**report.snapshot(), 'not_loaded': max(0, len(candidates) - MAX_RUNS)}

"""Run the source acceptance checks together; never run live tests or build installers."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from scripts.review_desktop import create_review_data
from thsr_ticket.run_records import atomic_json
from thsr_ticket.version import VERSION

TAIPEI = timezone(timedelta(hours=8))
LIVE_TEST = 'thsr_ticket.unittest.test_http_request::test_requests_work'
MANUAL = [
    {'id': 'U1', 'name': '版面、縮放與日曆／時間／遮蔽操作', 'status': 'not_run'},
    {'id': 'U2', 'name': '搜尋、分頁、複製及本機封存', 'status': 'not_run'},
    {'id': 'U3', 'name': '待確認狀態與必要確認', 'status': 'not_run'},
    {'id': 'U4', 'name': '完整備份、還原與防重送保留', 'status': 'not_run'},
    {'id': 'U5', 'name': '歷史整理、還原與永久清理', 'status': 'not_run'},
    {'id': 'U6', 'name': '通知實際顯示、點擊及視窗喚回', 'status': 'not_run'},
    {'id': 'U7', 'name': '完整鍵盤與螢幕閱讀器操作', 'status': 'not_run'},
    {'id': 'U8', 'name': '常用行程範本與套用欄位保留', 'status': 'not_run'},
    {'id': 'U9', 'name': '行程月曆與繳費／核對待辦', 'status': 'not_run'},
    {'id': 'U10', 'name': '本機期限確認與繳費提醒實際通知', 'status': 'not_run'},
    {'id': 'U11', 'name': '雙鐵設定、並行進度與台鐵人工核對', 'status': 'not_run'},
    {'id': 'L1', 'name': '官網核對、訂位／取消與回查', 'status': 'needs_data'},
    {'id': 'L2', 'name': '人工標註高鐵圖片的 OCR 評估', 'status': 'needs_data'},
    {'id': 'L3', 'name': '台鐵真人驗證、後續確認與成功結果解析', 'status': 'needs_data'},
]


def source_snapshot(base):
    files = set()
    for name in ('thsr_ticket', 'scripts', '.github/workflows'):
        files.update(path for path in (base / name).rglob('*')
                     if path.is_file() and path.suffix in ('.py', '.qml', '.svg', '.ps1', '.yml', '.json'))
    files.update(base.glob('requirements*.txt'))
    files.update(base / name for name in ('setup.py', 'TravelDesk.spec', '.config/flake') if (base / name).is_file())
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(base).as_posix().encode('utf-8') + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {'sha256': digest.hexdigest(), 'files': len(files)}


def repository_checks(base):
    missing, unindexed = [], []
    for file in [base / 'README.md', base / 'CHANGELOG.md', *sorted((base / 'docs').glob('*.md'))]:
        for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
            link = link.strip('<>').split('#')[0]
            if link and '://' not in link and not link.startswith('mailto:') and not (file.parent / link).exists():
                missing.append({'file': file.relative_to(base).as_posix(), 'link': link})
    inventory = (base / 'docs/file-inventory.md').read_text(encoding='utf-8')
    for folder in ('thsr_ticket', 'scripts'):
        for file in sorted((base / folder).rglob('*')):
            if file.suffix in ('.py', '.qml') and '../' + file.relative_to(base).as_posix() not in inventory:
                unindexed.append(file.relative_to(base).as_posix())
    return {'passed': not missing and not unindexed, 'missing_links': missing, 'unindexed_code': unindexed}


def test_results(path):
    cases = list(ET.parse(path).getroot().iter('testcase'))
    if not cases:
        raise ValueError('Empty JUnit report')
    skipped = [item.get('classname', '') + '::' + item.get('name', '')
               for item in cases if item.find('skipped') is not None]
    failed = sum(item.find('failure') is not None or item.find('error') is not None for item in cases)
    unexpected = [name for name in skipped if name != LIVE_TEST]
    return {'passed': len(cases) - len(skipped) - failed, 'failed': failed, 'skipped': skipped,
            'unexpected_skips': unexpected, 'accepted': failed == 0 and not unexpected}


def steps(output, native, temporary):
    result = [
        ('lint', ['-m', 'flake8', '-j1', '--config', '.config/flake', 'thsr_ticket', 'scripts']),
        ('tests', ['-m', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider', '-o', 'addopts=', '--require-desktop',
                   '--browser-tests', '--basetemp', str(temporary),
                   '--junitxml=' + str(output / 'tests.xml')]),
        ('management', ['-m', 'scripts.verify_management_transport', '--output', str(output / 'management.json')]),
        ('runtime', ['-m', 'thsr_ticket.desktop', '--self-test', str(output / 'runtime.json')]),
        ('performance', ['-m', 'scripts.benchmark_desktop', '--output', str(output / 'performance.json')]),
    ]
    for scale in ('1', '1.5'):
        arguments = ['-m', 'scripts.preview_desktop', '--scale', scale,
                     '--output', str(output / ('preview-' + scale))]
        result.append(('preview-' + scale, arguments))
    if native:
        for scale in ('1', '1.5'):
            arguments = ['-m', 'scripts.verify_desktop_session', '--scale', scale,
                         '--output', str(output / ('native-' + scale + '.json'))]
            result.append(('native-' + scale, arguments))
        result.append(('native-review', ['-m', 'scripts.verify_desktop_session', '--review',
                                         '--output', str(output / 'native-review.json')]))
    return result


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # Only the exact helper process created below and its descendants; no name-based kills.
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def run_step(base, output, name, arguments):
    started = time.monotonic()
    result = {'name': name, 'status': 'failed', 'log': name + '.log'}
    env = dict(os.environ, PYTHONUTF8='1', QT_QPA_PLATFORM='offscreen', PYTEST_ADDOPTS='')
    with (output / result['log']).open('x', encoding='utf-8') as log:
        process = None
        try:
            process = subprocess.Popen([sys.executable, *arguments], cwd=base, env=env, stdout=log,
                                       stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            result['exit_code'] = process.wait(timeout=300)
            result['status'] = 'passed' if result['exit_code'] == 0 else 'failed'
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            if process is not None:
                stop_process(process)
            result['status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'timeout'
        except OSError as error:
            result['error_type'] = type(error).__name__
    result['seconds'] = round(time.monotonic() - started, 2)
    return result


def verify_artifact(output, name):
    if name == 'tests':
        value = test_results(output / 'tests.xml')
        if not value['accepted']:
            raise ValueError('Test failures or unexpected skips')
        return value
    if name in ('management', 'runtime', 'performance') or name.startswith('native-'):
        value = json.loads((output / (name + '.json')).read_text(encoding='utf-8'))
        if value.get('qml_warnings') or value.get('warnings') or value.get('error_type'):
            raise ValueError('Artifact contains warnings or errors')
        if name == 'runtime' and not all(value.get(key) is True for key in (
                'qml', 'ocr_standard', 'ocr_beta', 'playwright_driver', 'private_storage')):
            raise ValueError('Runtime self-test incomplete')
        if name == 'management' and (len(value.get('cases', [])) != 4 or
                                     not all(item.get('passed') is True for item in value['cases'])):
            raise ValueError('Management scenarios incomplete')
        if name == 'performance' and (len(value.get('qml', [])) != 3 or
                                      not value.get('oversized_line_rejected')):
            raise ValueError('Performance checks incomplete')
        if name.startswith('native-') and not all(value.get('checks', {}).get(key) is True for key in (
                'preset_dialog_keyboard', 'preset_applied', 'calendar_keyboard', 'planner_frame_saved',
                'maximized_preserved', 'restored', 'active_window', 'keyboard_navigation', 'keyboard_search',
                'tab_to_date', 'keyboard_increase_ticket', 'keyboard_decrease_ticket', 'accessible_names',
                'date_month_length', 'date_cancel_preserves_value', 'date_wheels_scroll', 'date_wheel_drag',
                'date_frame_saved', 'date_applied', 'date_reopened_value',
                'keyboard_settings_tab', 'invalid_field_focus', 'frame_saved')):
            raise ValueError('Native checks incomplete')
    if name.startswith('preview-') and len(list((output / name).glob('*.png'))) < 5:
        raise ValueError('Preview images missing')
    return {}


def save_report(output, report):
    atomic_json(output / 'report.json', report)
    rows = ['# 集中驗收報告', '', '本報告只代表自動檢查；人工及實站項目不會自動改成通過。', '',
            '- 自動檢查：' + report['status'], '- 原始碼 SHA-256：`' + report['source']['sha256'] + '`', '',
            '| 檢查 | 結果 | 紀錄 |', '| --- | --- | --- |']
    rows.extend('| ' + item['name'] + ' | ' + item['status'] + ' | [' + item['log'] + '](' + item['log'] + ') |'
                for item in report['steps'])
    rows.extend(['', '## 待使用者驗收', '', '| 編號 | 項目 | 狀態 |', '| --- | --- | --- |'])
    rows.extend('| ' + item['id'] + ' | ' + item['name'] + ' | ' + item['status'] + ' |' for item in report['manual'])
    rows.extend(['', '操作步驟見專案 docs/acceptance.md。假資料位於 review-data/；以隔離驗收視窗開啟。', ''])
    (output / 'summary.md').write_text('\n'.join(rows), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', help='A new report directory; existing directories are never overwritten')
    parser.add_argument('--native', action='store_true', help='Also open isolated native Windows test windows')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise SystemExit('This source acceptance batch requires Windows and desktop dependencies.')
    base = Path(__file__).resolve().parents[1]
    name = datetime.now(TAIPEI).strftime('%Y%m%d-%H%M%S-') + uuid4().hex[:8]
    output = Path(args.output).resolve() if args.output else base / 'build/acceptance' / name
    output.mkdir(parents=True, exist_ok=False)
    # Nested backup fixtures can exceed MAX_PATH under the timestamped report folder.
    temporary = (base / 'build' / ('qa-' + uuid4().hex[:10])).resolve()
    if not temporary.is_relative_to(base.resolve()):
        raise ValueError('Test temporary directory must stay inside this workspace')
    temporary.mkdir(parents=True, exist_ok=False)
    plan = steps(output, args.native, temporary)
    create_review_data(output / 'review-data')
    report = {'version': 1, 'app_version': VERSION, 'created_at': datetime.now(TAIPEI).isoformat(),
              'scope': 'isolated source checks; no live tests, booking, cancellation or installer',
              'status': 'running', 'source': source_snapshot(base), 'steps': [],
              'test_temporary': temporary.relative_to(base).as_posix(),
              'manual': [dict(item) for item in MANUAL], 'repository': repository_checks(base)}
    save_report(output, report)
    print('Acceptance report: ' + str(output), flush=True)
    for name, arguments in plan:
        print('RUN ' + name, flush=True)
        result = run_step(base, output, name, arguments)
        if result['status'] == 'passed':
            try:
                details = verify_artifact(output, name)
                if details:
                    result['tests'] = details
            except (OSError, ValueError, ET.ParseError, KeyError, TypeError) as error:
                result.update(status='failed', error_type=type(error).__name__, artifact_invalid=True)
        report['steps'].append(result)
        save_report(output, report)
        print(result['status'].upper() + ' ' + name, flush=True)
        if result['status'] == 'interrupted':
            break
    report['source_unchanged'] = source_snapshot(base) == report['source']
    complete = len(report['steps']) == len(plan)
    report['status'] = ('passed' if complete and report['source_unchanged'] and report['repository']['passed']
                        and all(item['status'] == 'passed' for item in report['steps']) else 'failed')
    report['finished_at'] = datetime.now(TAIPEI).isoformat()
    save_report(output, report)
    print('Automatic checks: ' + report['status'] + '; manual acceptance remains pending.', flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())

"""Non-authoritative desktop task summaries. Booking state always takes precedence."""
from pathlib import Path

from thsr_ticket.booking_records import booking_codes, read_object
from thsr_ticket.run_records import atomic_json, timestamp


CODES = {'running', 'success', 'stopped', 'attempt_limit', 'website_rejected', 'network',
         'booking_unconfirmed', 'browser_start', 'ocr_load', 'preflight', 'operation_failed', 'interrupted'}


def task_path(config_path):
    return Path(config_path).with_suffix('.task.json')


def load_task(config_path):
    try:
        data = read_object(task_path(config_path))
        if data.get('version') != 1 or data.get('code') not in CODES or type(data.get('query_only')) is not bool:
            return {'code': 'summary_unreadable'}
        return {'code': data['code'], 'query_only': data['query_only']}
    except FileNotFoundError:
        return {}
    except (ValueError, OSError, TypeError):
        return {'code': 'summary_unreadable'}


def save_task(config_path, code, query_only):
    if code not in CODES or type(query_only) is not bool:
        raise ValueError('Invalid task summary')
    data = {'version': 1, 'code': code, 'query_only': query_only, 'updated_at': timestamp()}
    atomic_json(task_path(config_path), data)
    return data


def booking_guard(config_path):
    try:
        state = read_object(Path(config_path).with_suffix('.state.json'))
        if state.get('status') == 'booked':
            booking_codes(state)
            return 'booked'
        return 'pending' if state.get('status') == 'submission_pending' else 'unreadable'
    except FileNotFoundError:
        return ''
    except (ValueError, OSError, TypeError):
        return 'unreadable'


def task_view(snapshot, guard='', running=False, stopping=False):
    code = snapshot.get('code', 'idle')
    if running:
        code = 'stopping' if stopping else 'running'
    elif guard:
        code = guard
    elif code == 'running':
        code = 'interrupted'
    elif code == 'success':
        code = 'query_match' if snapshot.get('query_only') else 'finished'
    descriptions = {
        'idle': ('準備新任務', '設定行程後選擇只查票或自動訂位。', 'neutral', 'edit', '設定行程'),
        'running': ('任務執行中', '目前操作結束前不會啟動另一筆任務。', 'active', 'progress', '查看進度'),
        'stopping': ('正在停止', '等待目前操作與瀏覽器清理；停止不代表取消訂位。', 'warning', 'progress', '查看進度'),
        'booked': ('已有訂位紀錄', '本機保存了訂位成功結果；付款與取消狀態請以官網為準。',
                   'success', 'records', '管理這筆訂位'),
        'pending': ('訂位結果待確認', '訂位曾準備或嘗試送出。請先核對官網，確認後再處理本機紀錄。',
                    'warning', 'records', '核對訂位結果'),
        'unreadable': ('訂位紀錄需要檢查', '紀錄無法讀取或格式異常，已阻擋自動訂位。請保留原檔並核對官網。',
                       'danger', 'records', '查看紀錄'),
        'interrupted': ('前次任務狀態待確認', '未自動恢復或重送。請確認是否仍有其他視窗執行，並核對官網後再操作。',
                        'warning', 'official', '開啟官網核對'),
        'network': ('查票連線中斷', '連線重試已停止；請檢查網路與官網狀態，再檢查設定並重新啟動。',
                    'warning', 'edit', '檢查設定再啟動'),
        'website_rejected': ('網站拒絕操作', '請核對官網公告與訂位條件。此狀態不會自動重新送出請求。',
                             'warning', 'official', '查看官網'),
        'attempt_limit': ('已達查詢上限', '本次查詢已結束。可以調整時段、查詢輪數與間隔後重新啟動。',
                          'neutral', 'edit', '調整查詢設定'),
        'stopped': ('任務已停止', '已停止後續操作。若仍有待確認訂位，請先核對官網。', 'neutral', 'edit', '檢查行程'),
        'query_match': ('已找到符合車次', '上次為只查票模式，沒有送出訂位；即時座位可能已改變。',
                        'success', 'edit', '檢查行程'),
        'finished': ('上次任務已結束', '目前沒有阻擋紀錄；完整結果與封存紀錄可在我的訂位查看。',
                     'neutral', 'records', '查看訂位紀錄'),
        'booking_unconfirmed': ('請核對上次訂位', '上次回報結果待確認，但目前找不到有效阻擋紀錄，請先核對官網。',
                                'warning', 'official', '核對官網'),
        'browser_start': ('瀏覽器未能啟動', '請確認已安裝 Chrome，並到設定頁檢查執行環境。',
                          'danger', 'settings', '檢查環境'),
        'ocr_load': ('辨識元件未能載入', '請到設定頁檢查執行環境；本次未開始查票。',
                     'danger', 'settings', '檢查環境'),
        'summary_unreadable': ('上次任務摘要無法讀取', '不會自動恢復任務。訂位紀錄仍獨立保留，請先核對。',
                               'warning', 'records', '查看訂位紀錄'),
    }
    default = ('任務未完成', '請檢查設定與執行紀錄，確認官網狀態後再操作。', 'danger', 'edit', '檢查設定')
    title, detail, tone, action, label = descriptions.get(code, default)
    return dict(code=code, title=title, detail=detail, tone=tone, action=action, label=label,
                can_book=not running and not guard)

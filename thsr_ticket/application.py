"""UI-independent form conversion and cooperative booking worker."""
from pathlib import Path
from requests import RequestException
from thsr_ticket.automation import AutomationConfig, AutomationRunner, WebsiteRejected, wait_until


STATIONS = ['南港', '台北', '板橋', '桃園', '新竹', '苗栗', '台中', '彰化', '雲林', '嘉義', '台南', '左營']
FIELDS = [
    ('start_at', '開始查票時間（YYYY-MM-DD HH:MM:SS）'),
    ('outbound_date', '搭車日期（YYYY-MM-DD）'),
    ('start_station', '上車站'), ('dest_station', '下車站'),
    ('earliest_departure', '最早發車（HH:MM）'), ('latest_departure', '最晚發車（HH:MM）'),
    ('train_ids', '車次優先順序（逗號分隔，留空不限）'),
    ('adult_tickets', '成人票'), ('child_tickets', '孩童票'), ('disabled_tickets', '愛心票'),
    ('elder_tickets', '敬老票'), ('college_tickets', '大學生票'),
    ('class_type', '車廂'), ('personal_id', '身分證字號'), ('phone_num', '手機（可留空）'),
    ('interval_seconds', '每輪等待秒數'), ('max_attempts', '最多查詢輪數'), ('ocr_model', 'OCR 模型'),
]
INTEGER_FIELDS = ('adult_tickets', 'child_tickets', 'disabled_tickets', 'elder_tickets',
                  'college_tickets', 'max_attempts')


class FieldError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


def protected_config_path(path):
    name = Path(path).name.casefold()
    return name.endswith(('.state.json', '.example.json')) or name in ('state.json', 'result.json')


def form_config(values):
    data = dict(values)
    for name in INTEGER_FIELDS:
        try:
            data[name] = int(data[name])
        except ValueError:
            raise FieldError(name, '請輸入整數。') from None
    for key, options in [('start_station', STATIONS), ('dest_station', STATIONS), ('class_type', ['標準', '商務'])]:
        try:
            data[key] = options.index(data[key]) + (0 if key == 'class_type' else 1)
        except ValueError:
            raise FieldError(key, '請從選單選擇。') from None
    try:
        data['interval_seconds'] = float(data['interval_seconds'])
    except ValueError:
        raise FieldError('interval_seconds', '請輸入大於 0 的秒數。') from None
    try:
        data['train_ids'] = [int(item.strip()) for item in data['train_ids'].replace('，', ',').split(',')
                             if item.strip()]
    except ValueError:
        raise FieldError('train_ids', '請輸入逗號分隔的整數車次。') from None
    return AutomationConfig(**data)


class StoppableClient:
    def __init__(self, client, stop):
        self.client, self.stop = client, stop

    def __getattr__(self, name):
        method = getattr(self.client, name)
        if not callable(method):
            return method

        def call(*args, **kwargs):
            if self.stop.is_set():
                raise KeyboardInterrupt()
            return method(*args, **kwargs)
        return call


def run_background(config, path, query_only, stop, messages, client_factory=None, reader_factory=None,
                   runner_factory=None):
    def sleep(seconds):
        if stop.wait(seconds):
            raise KeyboardInterrupt()

    client = None
    runner = None
    failure = ''

    def emit(text):
        messages.put(('text', str(text) + '\n'))

    phase = 'preflight'
    outcome = '執行結束'
    try:
        if stop.is_set():
            raise KeyboardInterrupt()
        state = path.resolve().with_suffix('.state.json')
        if not query_only and state.exists():
            raise RuntimeError('已有訂位送出紀錄，請先查看並確認原訂位。')
        if client_factory is None:
            from thsr_ticket.remote.browser_request import BrowserRequest
            client_factory = BrowserRequest
        if reader_factory is None:
            from thsr_ticket.captcha import CaptchaReader
            reader_factory = CaptchaReader
        phase = 'browser_start'
        messages.put(('phase', '正在啟動瀏覽器'))
        client = client_factory(channel='chrome', interactive=False)
        phase = 'ocr_load'
        messages.put(('phase', '正在準備辨識模型'))
        reader = reader_factory(model=config.ocr_model)
        if not reader.prepare():
            raise RuntimeError('OCR 無法載入，請確認已安裝自動化套件。')
        emit(f'等待台灣時間 {config.start_at.isoformat()}；可按停止取消。')
        phase = 'schedule'
        messages.put(('phase', '等待啟動時間：' + config.start_at.strftime('%m/%d %H:%M')))
        wait_until(config.start_at, sleep=sleep)
        if stop.is_set():
            raise KeyboardInterrupt()
        runner = (runner_factory or AutomationRunner)(
            config, StoppableClient(client, stop), reader, state, sleep=sleep,
            event_sink=lambda event: messages.put(('event', event)), output=emit)
        phase = 'query'
        success = runner.run(query_only)
        outcome = ('找到符合車次' if query_only else '訂位成功，尚未付款') if success else '已達查詢上限'
        if not success:
            failure = 'attempt_limit'
            outcome = '已達查詢輪數上限，未送出訂位；可調整查詢輪數或間隔後重新啟動。'
    except KeyboardInterrupt:
        failure = 'stopped'
        outcome = '已停止；若已嘗試送出訂位，請確認官網狀態'
    except Exception as exc:
        # Do not echo arbitrary exceptions or website content into the UI log.
        outcome = '執行失敗，請查看執行紀錄；若已送出訂位，先確認官網狀態'
        failure = 'operation_failed'
        emit(f'錯誤類型：{type(exc).__name__}')
        hints = {'preflight': '請先確認是否已有訂位紀錄。',
                 'browser_start': 'Chrome 無法啟動，請確認已安裝 Chrome 及自動化套件。',
                 'ocr_load': 'OCR 無法載入，請依 README 安裝 requirements-automation-lock.txt。'}
        if phase in hints:
            outcome = hints[phase]
            failure = phase
        elif isinstance(exc, WebsiteRejected):
            failure = 'website_rejected'
            outcome = exc.user_message
        elif isinstance(exc, RequestException):
            failure = 'network'
            outcome = '連線持續失敗或網站拒絕連線，已停止；請檢查網路與官網狀態後再啟動。'
    finally:
        state = path.resolve().with_suffix('.state.json')
        if failure and state.exists():
            failure = 'booking_unconfirmed'
            outcome = '已有訂位送出紀錄，請到「我的訂位」核對結果；不會自動重送。'
        if client is not None:
            try:
                client.close()
            except Exception:
                emit('瀏覽器清理失敗，請檢查程式開啟的獨立視窗。')
        emit(outcome)
        messages.put(('completion', {'code': failure or 'success', 'message': outcome,
                                     'action': 'records' if failure == 'booking_unconfirmed' else
                                     'official' if failure == 'website_rejected' else
                                     'settings' if failure in ('browser_start', 'ocr_load') else
                                     'edit' if failure else ''}))
        messages.put(('done', outcome))

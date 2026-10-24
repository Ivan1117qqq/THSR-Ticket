"""Taiwan Railway's own form, with manual challenges and conservative POST guards."""
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from bs4 import BeautifulSoup

from thsr_ticket.automation import TAIPEI, clock_time
from thsr_ticket.record_lock import record_lock
from thsr_ticket.run_records import RunRecords, atomic_json

BOOKING_URL = 'https://www.railway.gov.tw/tra-tip-web/tip/tip001/tip121/query'
RECORD_URL = 'https://www.railway.gov.tw/tra-tip-web/tip/tip001/tip115/query'
HOSTS = {'www.railway.gov.tw', 'tip.railway.gov.tw', 'www.trc.com.tw', 'tip.trc.com.tw'}
NOTICE_ACK = '/tra-tip-web/tip/tip001/tip121/agree'
STATION_PATH = Path(__file__).with_name('configs') / 'tra_stations.json'


@lru_cache(maxsize=1)
def stations():
    return json.loads(STATION_PATH.read_text(encoding='utf-8'))['stations']


def official_url(url):
    try:
        parts = urlsplit(url)
        return (parts.scheme == 'https' and parts.hostname in HOSTS and parts.port in (None, 443)
                and not parts.username and not parts.password and parts.path.startswith('/tra-tip-web/'))
    except ValueError:
        return False


@dataclass(frozen=True)
class TraOptions:
    start_station: str
    dest_station: str
    quantity: int = 1
    earliest_departure: str = '09:30'
    latest_departure: str = '23:59'
    train_ids: str = ''
    interval_seconds: float = 3
    max_attempts: int = 60
    network_failure_limit: int = 3
    max_network_delay_seconds: float = 30

    def __post_init__(self):
        names = stations()
        if self.start_station not in names or self.dest_station not in names or self.start_station == self.dest_station:
            raise ValueError('請選擇不同的台鐵起訖站。')
        if type(self.quantity) is not int or not 1 <= self.quantity <= 9:
            raise ValueError('台鐵一般座票數須為 1～9。')
        for value in (self.earliest_departure, self.latest_departure):
            clock_time(value)
            if value[-2:] not in ('00', '30') and value != '23:59':
                raise ValueError('台鐵時段請選整點、半點或 23:59。')
        if self.earliest_departure > self.latest_departure:
            raise ValueError('請檢查台鐵出發時段先後順序。')
        ids = self.train_ids.replace('，', ',').split(',') if self.train_ids.strip() else []
        if len(ids) > 3 or any(not re.fullmatch(r'[0-9]{1,4}', x.strip()) or int(x) == 0 for x in ids):
            raise ValueError('台鐵最多指定三個正整數車次，以逗號分隔。')
        if len({int(x) for x in ids}) != len(ids):
            raise ValueError('台鐵車次不可重複。')
        if (isinstance(self.interval_seconds, bool) or not math.isfinite(self.interval_seconds)
                or self.interval_seconds <= 0
                or type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 10000):
            raise ValueError('請檢查台鐵重查秒數與查詢上限。')
        if (type(self.network_failure_limit) is not int or not 1 <= self.network_failure_limit <= 100
                or not math.isfinite(self.max_network_delay_seconds)
                or not 2 <= self.max_network_delay_seconds <= 3600):
            raise ValueError('台鐵連線失敗上限須為 1～100，退避上限須為 2～3600 秒。')


class TraRecords:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / 'tra-booking.local.state.json'

    def read(self):
        if self.path.is_symlink() or self.path.stat().st_size > 32768:
            raise ValueError('台鐵紀錄無法安全讀取；請保留原檔並核對官網。')
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or type(data.get('version')) is not int or data.get('version') != 1
                or data.get('operator') != 'tra'
                or data.get('status') not in ('pending', 'booked')):
            raise ValueError('台鐵紀錄格式未知；請保留原檔並核對官網。')
        if (not re.fullmatch(r'[0-9a-f]{32}', str(data.get('run_id', '')))
                or data.get('start_station') not in stations() or data.get('dest_station') not in stations()
                or type(data.get('quantity')) is not int or not 1 <= data['quantity'] <= 9
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(data.get('outbound_date', '')))
                or (data['status'] == 'booked'
                    and not re.fullmatch(r'[0-9A-Z]{6,12}', str(data.get('booking_code', ''))))):
            raise ValueError('台鐵紀錄不完整；請保留原檔並核對官網。')
        date.fromisoformat(data['outbound_date'])
        return data

    def pending(self, run_id, config, options):
        self.directory.mkdir(parents=True, exist_ok=True)
        data = {'version': 1, 'operator': 'tra', 'status': 'pending', 'run_id': run_id,
                'outbound_date': config.outbound_date, 'start_station': options.start_station,
                'dest_station': options.dest_station, 'quantity': options.quantity}
        with self.path.open('x', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())

    def clear_no_seat(self, run_id):
        data = self.read()
        if data['status'] != 'pending' or data['run_id'] != run_id:
            raise ValueError('紀錄與本次工作不符。')
        self.path.unlink()

    def booked(self, result):
        data = self.read()
        atomic_json(self.path, {**data, 'status': 'booked', **result})

    def archive(self):
        with record_lock(self.path):
            self.read()
            folder = self.directory / 'tra-booking.history'
            folder.mkdir(exist_ok=True)
            if folder.is_symlink():
                raise ValueError('封存資料夾不可為連結。')
            target = folder / (uuid4().hex + '.json')
            self.path.rename(target)
            return target


def inspect_result(html, config, options):
    """Only explicit success + labelled code + same journey count as a booked result."""
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup.select('script, style, nav, footer, header'):
        node.decompose()
    codes, code_label_seen = [], False
    for row in soup.select('tr'):
        cells = row.find_all(['th', 'td'], recursive=False)
        if len(cells) == 2 and cells[0].get_text(strip=True).rstrip('：:') in ('訂票代碼', '訂位代碼'):
            code_label_seen = True
            code = cells[1].get_text(strip=True)
            if re.fullmatch(r'[0-9A-Z]{6,12}', code):
                codes.append(code)
    expected_date = date.fromisoformat(str(config.outbound_date))
    headings = [x.get_text(' ', strip=True) for x in soup.select('h1, h2, h3, .alert-success')]
    same_journey = False
    for row in soup.select('tr'):
        cells = [cell.get_text(' ', strip=True).replace('台', '臺')
                 for cell in row.find_all(['td', 'th'], recursive=False)]
        if options.start_station not in cells or options.dest_station not in cells:
            continue
        if cells.index(options.start_station) >= cells.index(options.dest_station):
            continue
        dates = []
        for cell in cells:
            if re.fullmatch(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', cell):
                try:
                    dates.append(date(*map(int, re.split('[-/]', cell))))
                except ValueError:
                    pass
        if dates == [expected_date]:
            same_journey = True
            break
    successful = any(re.fullmatch(r'(?:恭喜[您你]?[，,！! ]*)?訂[票位]成功[！!。.]?', value) for value in headings)
    if len(set(codes)) == 1 and successful and same_journey:
        return 'booked', {'booking_code': codes[0]}
    alerts = ' '.join(x.get_text(' ', strip=True) for x in soup.select('#errorDiv, .alert-danger, [role=alert]'))
    no_seat = ('剩餘座位不足', '無符合條件之車次', '查無可售座位', '該班次已無座位')
    form = soup.select_one('form#queryForm')
    action = urlsplit(form.get('action', '')).path if form else ''
    if (not code_label_seen and action == '/tra-tip-web/tip/tip001/tip121/bookingTicket'
            and any(message in alerts for message in no_seat)):
        return 'no_seat', {}
    return 'manual', {}


class TraError(RuntimeError):
    messages = {
        'network': '台鐵首頁連線失敗，尚未送出訂位。',
        'browser_start': '台鐵 Chrome 無法啟動，請確認 Chrome 與自動化套件已安裝。',
        'browser_closed': '台鐵 Chrome 已關閉，請先核對已送出的訂位。',
        'form_changed': '台鐵表單欄位已變更或無法操作，請改用官網並回報執行紀錄。',
        'website_rejected': '台鐵網站拒絕連線，請稍後手動重啟或使用官網。',
        'manual_notice': '請在台鐵 Chrome 閱讀並關閉官網公告，程式會在完成後繼續預填。',
    }

    def __init__(self, code):
        self.code = code
        super().__init__(self.messages[code])


class TraBrowser:
    """Only ordinary form controls; no captcha tokens, bypasses or direct POST requests."""
    def __init__(self, before_post, factory=None):
        if factory is None:
            from thsr_ticket.remote.browser_request import BrowserRequest
            factory = BrowserRequest
        try:
            self.client = factory(channel='chrome', interactive=False)
        except (OSError, RuntimeError) as exc:
            raise TraError('browser_start') from exc
        self.page = self.client.page
        self.before_post = before_post
        self.post_error = None
        self.submitted = False
        self.page.route('**/*', self.route)

    def route(self, route):
        request = route.request
        main_post = request.is_navigation_request() and request.frame == self.page.main_frame
        path = urlsplit(request.url).path
        booking_post = (official_url(request.url) and path.startswith('/tra-tip-web/tip/tip001/')
                        and path != NOTICE_ACK)
        if request.method == 'POST' and (main_post or booking_post):
            try:
                if not official_url(request.url):
                    raise ValueError('非台鐵官網操作已停止。')
                self.before_post()
                self.submitted = True
            except Exception as exc:
                self.post_error = exc
                route.abort()
                return
        route.fallback()

    @staticmethod
    def choose(form, field):
        if not field.is_checked():
            label = field.locator('xpath=parent::label')
            identifier = field.get_attribute('id')
            if not label.count() and identifier:
                label = form.locator(f'label[for="{identifier}"]')
            if label.count():
                label.first.click()
            else:
                field.check()
        field.dispatch_event('change')

    def prepare(self, config, options):
        try:
            reply = self.page.goto(BOOKING_URL, wait_until='domcontentloaded')
        except self.client.browser_error as exc:
            raise TraError('browser_closed' if self.page.is_closed() else 'network') from exc
        if reply and reply.status in (403, 429):
            raise TraError('website_rejected')
        if reply and reply.status >= 500:
            raise TraError('network')
        if not official_url(self.page.url):
            raise TraError('form_changed')
        if self.has_notice():
            raise TraError('manual_notice')
        try:
            self.fill(config, options)
        except self.client.browser_error as exc:
            if not self.page.is_closed() and self.has_notice():
                raise TraError('manual_notice') from exc
            raise TraError('browser_closed' if self.page.is_closed() else 'form_changed') from exc

    def has_notice(self):
        if self.page.is_closed():
            raise TraError('browser_closed')
        return self.page.locator('.jconfirm:visible').count() > 0

    def fill(self, config, options):
        cookie = self.page.get_by_role('button', name='接受並關閉', exact=True)
        if cookie.count() and cookie.first.is_visible():
            cookie.first.click()
        form = self.page.locator('#queryForm')
        if form.count() != 1:
            raise TraError('form_changed')
        for name, value in (('custIdTypeEnum', 'PERSON_ID'), ('tripType', 'ONEWAY'),
                            ('orderType', 'BY_TRAIN_NO' if options.train_ids.strip() else 'BY_TIME')):
            field = form.locator(f'input[name="{name}"][value="{value}"]')
            self.choose(form, field)
        names = stations()
        values = {'pid': config.personal_id, 'startStation': names[options.start_station],
                  'endStation': names[options.dest_station], 'normalQty': str(options.quantity),
                  'rideDate1': str(config.outbound_date).replace('-', '/')}
        for name, value in values.items():
            form.locator('#' + name).fill(value)
        if options.train_ids.strip():
            for index, value in enumerate(options.train_ids.replace('，', ',').split(','), 1):
                form.locator('#trainNoList' + str(index)).fill(value.strip())
        else:
            form.locator('#startTime1').select_option(options.earliest_departure)
            form.locator('#endTime1').select_option(options.latest_departure)
            kinds = form.locator('input[type="checkbox"][name="ticketOrderParamList[0].trainTypeList"]')
            if not kinds.count():
                raise TraError('form_changed')
            for field in kinds.all():
                self.choose(form, field)

    def submit(self):
        if not official_url(self.page.url):
            raise ValueError('頁面已離開台鐵官網。')
        self.page.locator('#queryForm input[type=submit]').click(no_wait_after=True)

    def inspect(self, config, options):
        if self.post_error:
            raise self.post_error
        if not official_url(self.page.url):
            return 'manual', {}
        if self.page.is_closed():
            raise TraError('browser_closed')
        try:
            return inspect_result(self.page.content(), config, options)
        except self.client.browser_error:
            if self.page.is_closed():
                raise TraError('browser_closed')
            return 'manual', {}  # Navigation can briefly replace the execution context.

    def wait(self, milliseconds=250):
        if self.page.is_closed():
            raise TraError('browser_closed')
        self.page.wait_for_timeout(milliseconds)

    def focus(self):
        if self.page.is_closed():
            raise TraError('browser_closed')
        session = None
        try:
            session = self.client.context.new_cdp_session(self.page)
            window = session.send('Browser.getWindowForTarget')
            if window.get('bounds', {}).get('windowState') == 'minimized':
                bounds = {'windowId': window['windowId'], 'bounds': {'windowState': 'normal'}}
                session.send('Browser.setWindowBounds', bounds)
        except self.client.browser_error:
            pass  # Optional window activation must not terminate a booking task.
        finally:
            if session:
                try:
                    session.detach()
                except self.client.browser_error:
                    pass
        try:
            self.page.bring_to_front()
        except self.client.browser_error:
            if self.page.is_closed():
                raise TraError('browser_closed')

    def close(self):
        self.client.close()


def run_tra(config, options, directory, stop, emit, browser_factory=TraBrowser, clock=None,
            focus_event=None, prefill_only=False):
    clock = clock or (lambda: datetime.now(TAIPEI))
    records, run_id = TraRecords(directory), uuid4().hex
    browser = None
    history = RunRecords(records.path, output=lambda _: None)
    history.event('run_started', operator='tra', max_attempts=options.max_attempts,
                  interval_seconds=options.interval_seconds, prefill_only=prefill_only)

    def report(status, message, attempt=0, details=None):
        history.event('stage', operator='tra', phase=status, attempt=attempt)
        emit(status, message, attempt, details) if details else emit(status, message, attempt)

    def pump():
        if stop.is_set():
            raise KeyboardInterrupt()
        if focus_event is not None and focus_event.is_set():
            focus_event.clear()
            browser.focus()
        browser.wait()

    def prepare():
        failure = 0
        while True:
            if stop.is_set():
                raise KeyboardInterrupt()
            try:
                browser.prepare(config, options)
                return
            except TraError as exc:
                if exc.code == 'manual_notice':
                    report('manual', str(exc))
                    while browser.has_notice():
                        pump()
                    pump()
                    continue
                failure += 1
                if exc.code != 'network' or records.path.exists() or failure == options.network_failure_limit:
                    raise
                delay = min(options.max_network_delay_seconds, max(1, options.interval_seconds) * 2 ** (failure - 1))
                history.event('retry_scheduled', operator='tra', outcome='network', delay_seconds=delay)
                report('waiting', f'台鐵尚未送出訂位，連線失敗 {failure} 次；{delay:g} 秒後再連線')
                deadline = clock().timestamp() + delay
                while clock().timestamp() < deadline:
                    pump()
    try:
        records.directory.mkdir(parents=True, exist_ok=True)
        with record_lock(records.path):
            if records.path.exists() or records.path.is_symlink():
                raise ValueError('已有台鐵訂位紀錄。')
            if stop.is_set():
                raise KeyboardInterrupt()

            def before_post():
                if prefill_only:
                    raise ValueError('預填檢查模式不允許送出訂位。')
                if stop.is_set() or clock() < config.start_at:
                    raise ValueError('尚未到啟動時間或工作已停止。')
                if not records.path.exists():
                    records.pending(run_id, config, options)
                elif records.path.is_symlink() or records.read()['run_id'] != run_id:
                    raise ValueError('訂位紀錄已改變，停止本次送出。')

            report('running', '開啟台鐵獨立 Chrome，預填訂票資料')
            browser = browser_factory(before_post)
            prepare()
            if prefill_only:
                report('manual', '預填檢查中，不送出訂位；請檢查 Chrome 內容，完成後按停止')
                while True:
                    pump()
            report('scheduled', '等待啟動時間；可先檢查台鐵表單')
            while clock() < config.start_at:
                if stop.is_set():
                    raise KeyboardInterrupt()
                pump()
            for attempt in range(1, options.max_attempts + 1):
                if stop.is_set():
                    raise KeyboardInterrupt()
                report('running', '台鐵送出訂票；若出現驗證請在 Chrome 完成', attempt)
                browser.submit()
                report('manual', '請查看台鐵 Chrome：完成驗證或後續選車／確認；程式持續監看結果', attempt)
                while True:
                    status, result = browser.inspect(config, options)
                    if status == 'booked':
                        try:
                            records.booked(result)
                        except OSError:
                            report('pending', '已讀取台鐵代碼，但保存失敗；請保留面板代碼並核對官網，勿重訂',
                                   attempt, result)
                            return
                        report('booked', '台鐵訂位成功，尚未付款；其他工作不受影響', attempt)
                        return
                    if stop.is_set():
                        raise KeyboardInterrupt()
                    if status == 'no_seat' and records.path.exists():
                        records.clear_no_seat(run_id)
                        break
                    pump()
                if attempt < options.max_attempts:
                    report('waiting', '台鐵明確回覆無位，等待下一輪', attempt)
                    deadline = clock().timestamp() + options.interval_seconds
                    while clock().timestamp() < deadline:
                        if stop.is_set():
                            raise KeyboardInterrupt()
                        pump()
                    prepare()
            report('limit', '台鐵已達查詢上限，未確認訂位成功')
    except KeyboardInterrupt:
        report('pending' if records.path.exists() else 'stopped',
               '台鐵已停止；已送出過訂位時，請先核對官網，停止不會取消車票')
    except TraError as exc:
        history.event('run_failed', operator='tra', reason=exc.code)
        if records.path.exists():
            report('pending', '台鐵操作中斷且已有送出紀錄；請先核對官網，不會自動重送。')
        else:
            report('failed', str(exc))
    except Exception:
        history.event('run_failed', operator='tra', reason='operation_failed')
        report('pending' if records.path.exists() else 'failed',
               '台鐵工作中斷，請檢查 Chrome／官網；保留送出紀錄，不自動重送')
    finally:
        history.event('run_finished', operator='tra')
        if browser:
            try:
                browser.close()
            except Exception:
                pass

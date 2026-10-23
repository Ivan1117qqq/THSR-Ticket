"""One thread owns the official browser session and the operation lock until closed."""
import queue
import re
import threading
import time

from PySide6.QtCore import QObject, Property, Signal, Slot
from thsr_ticket.application import STATIONS
from thsr_ticket.booking_records import record_paths
from thsr_ticket.config_store import read_config_data
from thsr_ticket.official_booking import OfficialEvidence
from thsr_ticket.record_lock import record_lock
from thsr_ticket.storage_errors import StorageError, error_info


class BookingManager(QObject):
    changed = Signal()
    mutated = Signal()

    def __init__(self, context, parent=None, factory=None):
        super().__init__(parent)
        self.context, self.factory = context, factory
        self._thread = None
        self._commands, self._results = queue.Queue(), queue.Queue()
        self._stop = threading.Event()
        self._busy = False
        self._stage = 'idle'
        self._message = '輸入代碼並查詢官網，核對後才能同步或取消。'
        self._captcha = ''
        self._snapshot = {}
        self._review_time = 0

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def stage(self):
        return self._stage

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(str, notify=changed)
    def captcha(self):
        return self._captcha

    @Property('QVariantMap', notify=changed)
    def snapshot(self):
        return self._snapshot

    @Slot()
    def reset(self):
        if not self._busy:
            self._stage, self._snapshot, self._captcha = 'idle', {}, ''
            self._message = '輸入代碼並查詢官網，核對後才能同步或取消。'
            self.changed.emit()

    @Slot(str, str, 'QVariantMap')
    def start(self, code, fingerprint, ticket):
        if self.context()['running'] or not re.fullmatch('[0-9]{8}', code):
            self._message = '請提供目前訂位的八碼代碼，並先停止其他任務。'
            self.changed.emit()
            return
        config = self.context()['config']
        self._busy, self._stage = True, 'working'
        self._snapshot, self._captcha = {}, ''
        self._message = '正在開啟官網查詢工作階段…'
        self._stop.clear()
        self._commands = queue.Queue()

        def run():
            client = None
            try:
                state, _ = record_paths(config)
                with record_lock(state):
                    evidence = OfficialEvidence(config, code, fingerprint)
                    current = evidence.check()
                    personal = read_config_data(config)
                    expected = dict(ticket)
                    expected['date'] = expected.get('requested_outbound_date') or expected.get('date', '')
                    if current['status'] == 'submission_pending':
                        expected['date'] = current.get('outbound_date', '')
                        expected['train_id'] = str(current.get('train_id', ''))
                        for key in ('start_station', 'dest_station'):
                            number = current.get(key)
                            expected[key] = STATIONS[number - 1] if type(number) is int and 1 <= number <= 12 else ''
                    if self.factory is None:
                        from thsr_ticket.remote.booking_management import BookingManagement
                        factory = BookingManagement
                    else:
                        factory = self.factory
                    evidence.save('query_started')
                    client = factory()
                    image = client.open(personal['personal_id'], code, expected)
                    self._results.put(('captcha', image))
                    snapshot = None
                    reviewed = 0
                    deadline = time.monotonic() + 900
                    while not self._stop.is_set():
                        if time.monotonic() > deadline:
                            raise StorageError('official_unrecognized')
                        try:
                            action, payload = self._commands.get(timeout=0.1)
                        except queue.Empty:
                            continue
                        evidence.check()
                        if action == 'refresh':
                            self._results.put(('captcha', client.refresh_captcha()))
                        elif action == 'query':
                            try:
                                snapshot = client.query(payload)
                            except StorageError as error:
                                if error.code == 'official_query_rejected':
                                    self._results.put(('captcha', client.captcha()))
                                    self._results.put(('notice', '查詢未成功，請核對資料並重新輸入驗證碼。'))
                                    continue
                                raise
                            evidence.save('query_verified', snapshot)
                            self._results.put(('snapshot', snapshot))
                        elif action == 'sync' and snapshot:
                            if snapshot['status'] == 'cancelled':
                                evidence.cancel_success(snapshot)
                                self._results.put(('cancelled', snapshot))
                                break
                            evidence.sync(snapshot)
                            self._results.put(('synced', None))
                        elif action == 'review' and snapshot:
                            snapshot = client.prepare_cancel()
                            reviewed = time.monotonic()
                            self._results.put(('review', snapshot))
                        elif action == 'cancel' and snapshot and reviewed and time.monotonic() - reviewed <= 120:
                            evidence.prepare_cancel(snapshot)
                            try:
                                cancelled = client.cancel()
                                evidence.cancel_success(cancelled)
                            except Exception:
                                evidence.save('cancellation_unconfirmed')
                                raise StorageError('official_unconfirmed') from None
                            self._results.put(('cancelled', cancelled))
                            break
                        else:
                            raise StorageError('official_unrecognized')
            except Exception as error:
                info = error_info(error)
                self._results.put(('error', info['title'] + '。' + info['guidance']))
            finally:
                if client:
                    try:
                        client.close()
                    except Exception:
                        pass

        self._thread = threading.Thread(target=run, daemon=False)
        try:
            self._thread.start()
        except RuntimeError:
            self._thread = None
            self._busy = False
            self._stage, self._message = 'error', '無法啟動背景工作。'
        self.changed.emit()

    def send(self, action, value=None):
        self._stage = 'working'
        self._message = '正在核對官網…請等待，避免在瀏覽器中同時操作。'
        self._commands.put((action, value))
        self.changed.emit()

    @Slot(str)
    def query(self, captcha):
        if self._stage == 'captcha' and re.fullmatch('[A-Za-z0-9]{4}', captcha):
            self.send('query', captcha)

    @Slot()
    def refreshCaptcha(self):
        if self._stage == 'captcha':
            self.send('refresh')

    @Slot()
    def sync(self):
        if self._stage == 'snapshot':
            self.send('sync')

    @Slot()
    def reviewCancel(self):
        if (self._stage == 'snapshot' and self._snapshot.get('status') == 'unpaid'
                and self._snapshot.get('trip_matches')):
            self.send('review')

    @Slot(bool)
    def confirmCancel(self, confirmed):
        if confirmed and self._stage == 'review':
            if time.monotonic() - self._review_time <= 120:
                self.send('cancel')
            else:
                self._stage = 'snapshot'
                self._message = '確認已過期，請重新按「準備取消」核對官網，再確認。'
                self.changed.emit()

    @Slot()
    def stop(self):
        self._stop.set()
        self._message = '正在結束工作階段；已送出的取消不會撤回，請等待結果。'
        self.changed.emit()

    def poll(self):
        while not self._results.empty():
            action, value = self._results.get_nowait()
            if action == 'captcha':
                self._stage, self._captcha = 'captcha', value
                self._message = '依圖片輸入驗證碼後查詢。工作階段最多保留 15 分鐘。'
            elif action in ('snapshot', 'review', 'cancelled'):
                self._stage, self._snapshot = action, value
                self._review_time = time.monotonic()
                self._message = {'snapshot': '已取得官網狀態；請核對代碼與行程。',
                                 'review': '確認後將真正取消這筆未付款訂位。確認有效時間為兩分鐘。',
                                 'cancelled': '官網已確認取消成功，原防重送紀錄已封存。'}[action]
                if action == 'cancelled':
                    self.mutated.emit()
            elif action == 'synced':
                self._stage, self._message = 'snapshot', '已保存官網核對結果；防重送保護仍保留。'
                self.mutated.emit()
            else:
                self._message = value
                if action == 'error':
                    self._stage = 'error'
            self.changed.emit()
        if self._thread is not None and not self._thread.is_alive():
            self._thread.join()
            self._thread = None
            self._busy = False
            self._captcha = ''
            if self._stage not in ('error', 'cancelled'):
                self._stage, self._message = 'idle', '工作階段已結束；本機防重送狀態保留。'
            self.changed.emit()

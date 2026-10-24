"""Independent operator jobs; one failure never kills the other operator's attempt."""
import queue
import threading


class DualRailSession:
    def __init__(self, jobs):
        if not jobs or set(jobs) - {'thsr', 'tra'}:
            raise ValueError('At least one supported operator is required')
        self.jobs = jobs
        self.messages = queue.Queue()
        self.stops = {key: threading.Event() for key in jobs}
        self.threads = {}
        self.rows = {key: {'operator': key, 'status': 'ready', 'message': '準備啟動', 'attempt': 0}
                     for key in jobs}

    @property
    def busy(self):
        return any(thread.is_alive() for thread in self.threads.values())

    def start(self):
        if self.threads:
            raise RuntimeError('Session already started')
        for key, job in self.jobs.items():
            thread = threading.Thread(target=self._run, args=(key, job), daemon=False)
            self.threads[key] = thread
            try:
                thread.start()
            except RuntimeError:
                self.threads.pop(key)
                self.rows[key].update(status='failed', message='背景工作無法啟動')
                for other in self.jobs:
                    if other not in self.threads and other != key:
                        self.rows[other].update(status='stopped', message='未啟動')
                self.stop()
                break

    def _run(self, key, job):
        def emit(status, message, attempt=0, details=None):
            self.messages.put((key, status, message, attempt, details or {}))
        try:
            job(self.stops[key], emit)
        except BaseException:
            # Exceptions and website text can contain credentials. Keep UI messages fixed.
            emit('interrupted', '工作非預期結束；送出過訂位時請先核對官網')
        finally:
            self.messages.put((key, '_finished', '', 0, {}))

    def poll(self):
        changed = False
        while True:
            try:
                key, status, message, attempt, details = self.messages.get_nowait()
            except queue.Empty:
                break
            changed = True
            if status == '_finished':
                if self.rows[key]['status'] not in ('booked', 'failed', 'pending', 'stopped', 'interrupted', 'limit'):
                    self.rows[key].update(status='interrupted', message='工作已結束，請核對結果')
            else:
                self.rows[key].update(status=status, message=message)
                if attempt:
                    self.rows[key]['attempt'] = attempt
                if details.get('booking_code'):
                    self.rows[key]['booking_code'] = details['booking_code']
        for thread in self.threads.values():
            if not thread.is_alive() and thread.ident is not None:
                thread.join()
        return changed

    def stop(self, operator=None):
        for key, event in self.stops.items():
            if operator is None or operator == key:
                event.set()


class ThsrMessages:
    """Adapt the existing worker without modifying its booking or persistence contracts."""
    def __init__(self, emit):
        self.emit = emit

    def put(self, item):
        kind, value = item
        if kind == 'phase':
            self.emit('running', value)
        elif kind == 'event':
            attempt = value.get('attempt', 0)
            if attempt:
                self.emit('running', '高鐵查詢中', attempt)
        elif kind == 'completion':
            status = {'success': 'booked', 'booking_unconfirmed': 'pending', 'stopped': 'stopped',
                      'attempt_limit': 'limit'}.get(value['code'], 'failed')
            self.emit(status, value['message'])


def thsr_job(config, path, worker):
    def run(stop, emit):
        worker(config, path, False, stop, ThsrMessages(emit))
    return run

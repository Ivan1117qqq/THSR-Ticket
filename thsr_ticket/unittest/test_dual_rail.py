"""Parallel jobs and TRA's conservative persistence, tested without real tickets."""
import threading
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from thsr_ticket.automation import TAIPEI
from thsr_ticket.dual_rail import DualRailSession
from thsr_ticket.tra_booking import TraError, TraOptions, TraRecords, inspect_result, official_url, run_tra, stations


def config():
    return SimpleNamespace(outbound_date='2099-01-15', personal_id='PRIVATE-ID',
                           start_at=datetime(2099, 1, 14, 9, tzinfo=TAIPEI))


def success_html(date='2099/01/15', destination='臺中'):
    return ('<main><h2>訂票成功</h2><table><tr><th>訂票代碼</th><td>12345678</td></tr>'
            f'<tr><td>{date}</td><td>臺北</td><td>{destination}</td><td>117</td></tr></table></main>')


def test_jobs_really_overlap_and_first_success_does_not_stop_peer():
    entered = threading.Barrier(2)
    first_done, release = threading.Event(), threading.Event()

    def thsr(stop, emit):
        entered.wait(3)
        emit('booked', '高鐵成功')
        first_done.set()

    def tra(stop, emit):
        entered.wait(3)
        assert release.wait(3) and not stop.is_set()
        emit('booked', '台鐵成功')

    session = DualRailSession({'thsr': thsr, 'tra': tra})
    session.start()
    try:
        assert first_done.wait(3)
        session.poll()
        assert session.rows['thsr']['status'] == 'booked' and session.busy
        assert not session.stops['tra'].is_set()
    finally:
        release.set()
        for thread in session.threads.values():
            thread.join(3)
    session.poll()
    assert {row['status'] for row in session.rows.values()} == {'booked'}


def test_failure_and_stop_are_isolated_per_operator():
    entered = threading.Event()

    def failed(stop, emit):
        raise ValueError('PRIVATE-ID MUST NOT APPEAR')

    def waiting(stop, emit):
        entered.set()
        assert stop.wait(3)
        emit('stopped', '已停止')

    session = DualRailSession({'thsr': failed, 'tra': waiting})
    session.start()
    assert entered.wait(3)
    assert not session.stops['tra'].is_set()
    session.stop('tra')
    for thread in session.threads.values():
        thread.join(3)
    session.poll()
    assert session.rows['thsr']['status'] == 'interrupted'
    assert session.rows['tra']['status'] == 'stopped'
    assert 'PRIVATE' not in str(session.rows)


@pytest.mark.parametrize('kwargs', [dict(quantity=0), dict(quantity=10), dict(quantity=True),
                                    dict(start_station='台北'), dict(dest_station='臺北'),
                                    dict(earliest_departure='09:31'), dict(latest_departure='09:00'),
                                    dict(train_ids='1,2,3,4'), dict(train_ids='117,0117'),
                                    dict(interval_seconds=float('nan')), dict(max_attempts=0)])
def test_tra_validation_rejects_silent_coercion(kwargs):
    with pytest.raises(ValueError):
        TraOptions(**{'start_station': '臺北', 'dest_station': '臺中', **kwargs})


@pytest.mark.parametrize('url', [
    'http://www.railway.gov.tw/tra-tip-web/',
    'https://www.railway.gov.tw.evil.test/tra-tip-web/',
    'https://evil.test/?x=https://www.railway.gov.tw',
    'https://user@www.railway.gov.tw/tra-tip-web/',
    'https://www.railway.gov.tw:444/tra-tip-web/',
])
def test_only_exact_official_https_origins(url):
    assert not official_url(url)


def test_station_codes_are_operator_specific():
    assert stations()['臺北'] == '1000-臺北'
    assert stations()['新左營'] != stations()['高雄']


@pytest.mark.parametrize('html', [success_html(date='2098/01/15'), success_html(destination='臺南'),
                                  success_html().replace('<h2>訂票成功</h2>', ''),
                                  success_html().replace('<th>訂票代碼</th>', '<th>其他</th>'),
                                  '<footer>' + success_html() + '</footer>',
                                  '<h2>訂票成功</h2><table><tr><th>訂票代碼</th><td>12345678</td></tr>'
                                  '<tr><td>2099/01/15</td></tr><tr><td>臺北 臺中</td></tr></table>'])
def test_ambiguous_success_never_becomes_booked(html):
    assert inspect_result(html, config(), TraOptions('臺北', '臺中'))[0] == 'manual'


def test_no_seat_requires_form_and_explicit_scoped_error():
    options = TraOptions('臺北', '臺中')
    assert inspect_result(success_html(), config(), options) == ('booked', {'booking_code': '12345678'})
    message = '<div id="errorDiv">剩餘座位不足</div>'
    assert inspect_result(message, config(), options)[0] == 'manual'
    form = '<form id="queryForm" action="/tra-tip-web/tip/tip001/tip121/bookingTicket"></form>'
    assert inspect_result(form + message, config(), options)[0] == 'no_seat'
    assert inspect_result('<form id="queryForm"></form>' + message, config(), options)[0] == 'manual'
    footer = '<form id="queryForm"></form><footer>' + message + '</footer>'
    assert inspect_result(footer, config(), options)[0] == 'manual'


def test_rejection_with_code_label_never_clears_a_pending_reservation():
    form = '<form id="queryForm" action="/tra-tip-web/tip/tip001/tip121/bookingTicket"></form>'
    page = form + '<div id="errorDiv">剩餘座位不足</div><table><tr><th>訂票代碼</th><td>?</td></tr></table>'
    assert inspect_result(page, config(), TraOptions('臺北', '臺中'))[0] == 'manual'
    assert inspect_result(success_html().replace('訂票成功', '未訂票成功'), config(), TraOptions('臺北', '臺中'))[0] == 'manual'


class SimulatedBrowser:
    def __init__(self, guard, directory, stop, outcomes):
        self.guard, self.directory, self.stop, self.outcomes = guard, directory, stop, list(outcomes)
        self.prepared, self.posts, self.closed = 0, 0, False

    def prepare(self, config, options):
        self.prepared += 1

    def submit(self):
        self.guard()
        assert TraRecords(self.directory).read()['status'] == 'pending'
        self.posts += 1

    def inspect(self, config, options):
        value = self.outcomes.pop(0)
        if value == 'stop':
            self.stop.set()
            return 'manual', {}
        return value, {'booking_code': '12345678'} if value == 'booked' else {}

    def wait(self):
        pass

    def close(self):
        self.closed = True


def run_simulated(tmp_path, outcomes, monkeypatch=None):
    stop, events, browsers = threading.Event(), [], []
    current = [config().start_at]

    def factory(guard):
        browser = SimulatedBrowser(guard, tmp_path, stop, outcomes)
        browsers.append(browser)
        return browser

    def clock():
        from datetime import timedelta
        current[0] += timedelta(seconds=1)
        return current[0]

    run_tra(config(), TraOptions('臺北', '臺中'), tmp_path, stop,
            lambda *args: events.append(args), factory, clock)
    return events, browsers


def test_only_known_no_seat_allows_another_post(tmp_path):
    events, browsers = run_simulated(tmp_path, ['no_seat', 'booked'])
    assert browsers[0].posts == 2 and browsers[0].prepared == 2 and browsers[0].closed
    assert events[-1][0] == 'booked'
    records = TraRecords(tmp_path)
    assert records.read()['booking_code'] == '12345678'
    assert 'PRIVATE-ID' not in records.path.read_text(encoding='utf-8')


def test_unknown_result_and_stop_preserve_guard_without_retry(tmp_path):
    events, browsers = run_simulated(tmp_path, ['stop'])
    assert browsers[0].posts == 1 and events[-1][0] == 'pending'
    assert TraRecords(tmp_path).read()['status'] == 'pending'
    before = TraRecords(tmp_path).path.read_bytes()
    events, browsers = run_simulated(tmp_path, ['booked'])
    assert not browsers and TraRecords(tmp_path).path.read_bytes() == before


def test_guard_failure_prevents_post(tmp_path, monkeypatch):
    monkeypatch.setattr(TraRecords, 'pending', lambda *args: (_ for _ in ()).throw(OSError()))
    events, browsers = run_simulated(tmp_path, ['booked'])
    assert browsers[0].posts == 0 and events[-1][0] == 'failed'


def test_archive_preserves_record_and_never_cancels(tmp_path):
    records = TraRecords(tmp_path)
    records.pending(uuid4().hex, config(), TraOptions('臺北', '臺中'))
    records.booked({'booking_code': '12345678'})
    before = records.path.read_bytes()
    archived = records.archive()
    assert not records.path.exists() and archived.read_bytes() == before


@pytest.mark.parametrize('html', [
    success_html(destination='臺北新站'),
    success_html().replace('<td>臺北</td><td>臺中</td>', '<td>臺中</td><td>臺北</td>'),
    success_html(date='2099/01/150'),
])
def test_success_needs_exact_station_cells_in_the_right_direction(html):
    assert inspect_result(html, config(), TraOptions('臺北', '臺中'))[0] == 'manual'


def test_success_accepts_hyphen_dates_without_guessing_year():
    assert inspect_result(success_html(date='2099-1-15'), config(), TraOptions('臺北', '臺中'))[0] == 'booked'


def test_pre_submit_network_failure_retries_with_a_bound(tmp_path, monkeypatch):
    original = SimulatedBrowser.prepare
    failures = []

    def flaky(browser, conf, options):
        failures.append(True)
        if len(failures) < 3:
            raise TraError('network')
        original(browser, conf, options)

    monkeypatch.setattr(SimulatedBrowser, 'prepare', flaky)
    events, browsers = run_simulated(tmp_path, ['booked'])
    assert len(failures) == 3 and browsers[0].posts == 1 and events[-1][0] == 'booked'
    logs = ''.join(path.read_text(encoding='utf-8') for path in tmp_path.glob('*.runs/*/events.jsonl'))
    assert 'retry_scheduled' in logs and 'PRIVATE-ID' not in logs and '12345678' not in logs


@pytest.mark.parametrize('code', ['network', 'website_rejected', 'form_changed'])
def test_network_limit_and_non_transient_failures_stop_without_submitting(tmp_path, monkeypatch, code):
    failures = []

    def broken(browser, conf, options):
        failures.append(True)
        raise TraError(code)

    monkeypatch.setattr(SimulatedBrowser, 'prepare', broken)
    events, browsers = run_simulated(tmp_path, ['booked'])
    assert len(failures) == (3 if code == 'network' else 1)
    assert browsers[0].posts == 0 and events[-1][0] == 'failed'
    assert not TraRecords(tmp_path).path.exists()


def test_network_failure_after_post_never_retries(tmp_path, monkeypatch):
    def failed_result(browser, conf, options):
        raise TraError('network')

    monkeypatch.setattr(SimulatedBrowser, 'inspect', failed_result)
    events, browsers = run_simulated(tmp_path, [])
    assert browsers[0].posts == 1 and browsers[0].prepared == 1 and events[-1][0] == 'pending'
    assert TraRecords(tmp_path).read()['status'] == 'pending'


def test_known_code_is_reported_if_state_update_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(TraRecords, 'booked', lambda *args: (_ for _ in ()).throw(OSError()))
    events, browsers = run_simulated(tmp_path, ['booked'])
    assert browsers[0].posts == 1
    assert events[-1][0] == 'pending' and events[-1][3] == {'booking_code': '12345678'}
    assert TraRecords(tmp_path).read()['status'] == 'pending'


def test_focus_command_is_executed_by_the_browser_worker(tmp_path):
    from datetime import timedelta
    stop, focus, events, focused = threading.Event(), threading.Event(), [], []
    now = [config().start_at]
    focus.set()

    def factory(guard):
        browser = SimulatedBrowser(guard, tmp_path, stop, ['manual', 'booked'])
        browser.focus = lambda: focused.append(threading.get_ident())
        return browser

    def clock():
        now[0] += timedelta(seconds=1)
        return now[0]

    run_tra(config(), TraOptions('臺北', '臺中'), tmp_path, stop,
            lambda *args: events.append(args), factory, clock, focus_event=focus)
    assert focused == [threading.get_ident()] and not focus.is_set()
    assert events[-1][0] == 'booked'


def test_prefill_preview_never_calls_submit_and_rejects_manual_post(tmp_path):
    stop, events, blocked = threading.Event(), [], []

    def factory(guard):
        browser = SimulatedBrowser(guard, tmp_path, stop, [])

        def wait():
            with pytest.raises(ValueError):
                guard()  # A manual submit in the preview's Chrome is blocked too.
            blocked.append(True)
            assert browser.posts == 0
            stop.set()

        browser.wait = wait
        return browser

    run_tra(config(), TraOptions('臺北', '臺中'), tmp_path, stop,
            lambda *args: events.append(args), factory, lambda: config().start_at, prefill_only=True)
    assert blocked and events[-1][0] == 'stopped'
    assert not TraRecords(tmp_path).path.exists()


def test_manual_announcement_waits_without_consuming_network_retry_budget(tmp_path, monkeypatch):
    original = SimulatedBrowser.prepare
    prepared = []

    def notice_once(browser, conf, options):
        prepared.append(True)
        if len(prepared) == 1:
            raise TraError('manual_notice')
        original(browser, conf, options)

    monkeypatch.setattr(SimulatedBrowser, 'prepare', notice_once)
    monkeypatch.setattr(SimulatedBrowser, 'has_notice', lambda self: False, raising=False)
    events, browsers = run_simulated(tmp_path, ['booked'])
    assert len(prepared) == 2 and browsers[0].posts == 1 and events[-1][0] == 'booked'
    assert any(event[0] == 'manual' and '公告' in event[1] for event in events)

"""Real Chrome, all network responses intercepted; no live website or ticket operations."""
import pytest

from thsr_ticket.tra_booking import BOOKING_URL, NOTICE_ACK, TraBrowser, TraError, TraOptions, TraRecords
from thsr_ticket.unittest.test_dual_rail import config, success_html

pytestmark = pytest.mark.browser

FORM = '''<form id="queryForm" method="post" action="/tra-tip-web/tip/tip001/tip121/bookingTicket">
<input name="custIdTypeEnum" value="PERSON_ID" type="radio">
<input name="tripType" value="ONEWAY" type="radio">
<input name="orderType" value="BY_TIME" type="radio"><input name="orderType" value="BY_TRAIN_NO" type="radio">
<input id="pid"><input id="startStation"><input id="endStation"><input id="normalQty"><input id="rideDate1">
<input id="trainNoList1"><input id="trainNoList2"><input id="trainNoList3">
<select id="startTime1"><option>09:30</option></select><select id="endTime1"><option>23:59</option></select>
<label><input type="checkbox" name="ticketOrderParamList[0].trainTypeList" value="11">自強3000</label>
<label><input type="checkbox" name="ticketOrderParamList[0].trainTypeList" value="3">自強</label>
<input type="submit" value="訂票"></form>'''


@pytest.mark.parametrize('guard_fails', [False, True])
def test_native_controls_and_post_guard_in_chrome(tmp_path, guard_fails, monkeypatch):
    from thsr_ticket.remote.browser_request import BrowserRequest
    posts, records = [], TraRecords(tmp_path)

    def factory(**kwargs):
        client = BrowserRequest(headless=True, **kwargs)

        def respond(route):
            assert route.request.url.startswith('https://www.railway.gov.tw/')
            if route.request.method == 'POST':
                assert records.path.exists()  # Guard reached disk before any POST can leave.
                posts.append(route.request.url)
            route.fulfill(status=200, content_type='text/html; charset=utf-8',
                          body=success_html() if route.request.method == 'POST' else FORM)
        client.context.route('**/*', respond)
        return client

    def guard():
        if guard_fails:
            raise OSError('simulated persistence error')
        records.pending('a' * 32, config(), TraOptions('臺北', '臺中'))

    browser = TraBrowser(guard, factory)
    try:
        browser.prepare(config(), TraOptions('臺北', '臺中'))
        assert browser.page.url == BOOKING_URL
        assert browser.page.locator('#pid').input_value() == 'PRIVATE-ID'
        assert browser.page.locator('#startStation').input_value() == '1000-臺北'
        assert browser.page.locator('#rideDate1').input_value() == '2099/01/15'
        assert browser.page.locator('input[type=checkbox]:checked').count() == 2
        browser.focus()
        with monkeypatch.context() as patch:
            def no_window_api(*args):
                raise browser.client.browser_error('simulated unsupported window API')
            patch.setattr(browser.client.context, 'new_cdp_session', no_window_api)
            browser.focus()  # Optional window activation failure must not stop submission.
        browser.submit()
        for _ in range(20):
            browser.wait()
            if posts or browser.post_error:
                break
        if guard_fails:
            assert browser.post_error and not posts and not records.path.exists()
        else:
            assert len(posts) == 1
            assert browser.inspect(config(), TraOptions('臺北', '臺中'))[0] == 'booked'
    finally:
        browser.close()


@pytest.mark.parametrize('status,code', [(403, 'website_rejected'), (429, 'website_rejected'), (503, 'network')])
def test_http_failures_are_classified_before_post(status, code):
    from thsr_ticket.remote.browser_request import BrowserRequest
    posts = []

    def factory(**kwargs):
        client = BrowserRequest(headless=True, **kwargs)

        def respond(route):
            posts.append(route.request.method) if route.request.method == 'POST' else None
            route.fulfill(status=status, content_type='text/html', body='unavailable')
        client.context.route('**/*', respond)
        return client

    browser = TraBrowser(lambda: None, factory)
    try:
        with pytest.raises(TraError) as error:
            browser.prepare(config(), TraOptions('臺北', '臺中'))
        assert error.value.code == code and not posts
    finally:
        browser.close()


def test_window_closed_has_actionable_fixed_error():
    from thsr_ticket.remote.browser_request import BrowserRequest

    def factory(**kwargs):
        client = BrowserRequest(headless=True, **kwargs)
        client.context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body=FORM))
        return client

    browser = TraBrowser(lambda: None, factory)
    try:
        browser.prepare(config(), TraOptions('臺北', '臺中'))
        browser.page.close()
        with pytest.raises(TraError) as error:
            browser.wait()
        assert error.value.code == 'browser_closed'
    finally:
        browser.close()


@pytest.mark.parametrize('preview', [True, False])
def test_ajax_booking_post_also_passes_through_persistence_guard(tmp_path, preview):
    from thsr_ticket.remote.browser_request import BrowserRequest
    records, posts = TraRecords(tmp_path), []

    def factory(**kwargs):
        client = BrowserRequest(headless=True, **kwargs)

        def respond(route):
            if route.request.method == 'POST':
                assert records.path.exists()
                posts.append(route.request.url)
            route.fulfill(status=200, content_type='text/html', body=FORM)
        client.context.route('**/*', respond)
        return client

    def guard():
        if preview:
            raise ValueError('Preview blocks all booking POSTs')
        records.pending('a' * 32, config(), TraOptions('臺北', '臺中'))

    browser = TraBrowser(guard, factory)
    try:
        browser.prepare(config(), TraOptions('臺北', '臺中'))
        browser.page.evaluate("""() => fetch('/tra-tip-web/tip/tip001/tip121/bookingTicket',
            {method:'POST'}).catch(() => null)""")
        assert bool(posts) is (not preview)
        assert records.path.exists() is (not preview)
    finally:
        browser.close()


@pytest.mark.parametrize('path', [NOTICE_ACK, '/tra-tip-web/tip/recaptcha/verify'])
def test_non_booking_notice_and_verification_posts_do_not_create_booking_guard(path):
    from thsr_ticket.remote.browser_request import BrowserRequest
    posts = []

    def factory(**kwargs):
        client = BrowserRequest(headless=True, **kwargs)

        def respond(route):
            if route.request.method == 'POST':
                posts.append(route.request.url)
            route.fulfill(status=200, content_type='text/html', body=FORM)
        client.context.route('**/*', respond)
        return client

    def guard():
        raise AssertionError('Non-booking acknowledgements must not trigger booking persistence')

    browser = TraBrowser(guard, factory)
    try:
        browser.prepare(config(), TraOptions('臺北', '臺中'))
        browser.page.evaluate('(path) => fetch(path,{method:"POST"}).catch(() => null)', path)
        assert len(posts) == 1 and not browser.post_error
    finally:
        browser.close()

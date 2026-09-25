import io
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image
from requests import ConnectionError as RequestConnectionError

from thsr_ticket.unittest.test_current_flow import html


pytestmark = pytest.mark.browser


@pytest.fixture(params=[True, False], ids=['playwright-headless', 'native-chrome'])
def browser_client(request):
    pytest.importorskip('playwright')
    from thsr_ticket.remote.browser_request import BrowserRequest
    client = BrowserRequest(channel='chrome', headless=request.param, timeout=5)
    try:
        yield client
    finally:
        client.close()
        if client.native is not None:
            assert client.native.process.poll() is not None
            assert not client.native.profile.exists()


def install_routes(client, fail_post=False):
    calls = []
    image = io.BytesIO()
    Image.new('RGB', (145, 55), 'white').save(image, format='PNG')
    extra = ''.join(f'<input name="{name}">' for name in (
        'selectStartStation', 'selectDestinationStation', 'toTimeInputField',
        'toTimeTable', 'homeCaptcha:securityCode',
    ))
    extra += '<button type="submit" name="submitAction" value="search">Search</button>'
    extra += '<input type="radio" name="bookingMethod" value="radio20">'
    extra = extra.replace('<input name="toTimeInputField">',
                          '<input type="hidden" name="toTimeInputField" value="2000/01/01">')
    booking = html('booking').decode('utf-8').replace('</form>', extra + '</form>')
    booking = booking.replace('<form id=', '<form method="post" id=')
    notice = ('<div id="cookiePolicy" style="position:fixed;inset:0;z-index:999;background:white">'
              '<button id="cookieAccpetBtn" onclick="this.parentElement.remove()">Accept</button></div>')
    booking = booking.replace('</body>', notice + '</body>')

    def handle(route):
        request = route.request
        calls.append(request)
        parsed = urlparse(request.url)
        if parsed.hostname != 'irs.thsrc.com.tw':
            route.abort()
        elif 'captcha' in parsed.path:
            route.fulfill(body=image.getvalue(), content_type='image/png')
        elif request.method == 'POST':
            if fail_post:
                route.abort('failed')
            else:
                route.fulfill(body=html('trains'), content_type='text/html; charset=utf-8')
        else:
            route.fulfill(body=booking, content_type='text/html; charset=utf-8')
    client.page.route('**/*', handle)
    return calls


def booking_params():
    return {'selectStartStation': 2, 'selectDestinationStation': 12,
            'toTimeInputField': '2099/01/01', 'toTimeTable': '930A',
            'homeCaptcha:securityCode': 'A7B3', 'BookingS1Form:hf:0': ''}


def test_browser_keeps_image_and_hidden_fields_in_same_session(browser_client):
    calls = install_routes(browser_client)
    page = browser_client.request_booking_page()
    assert browser_client.page.locator('#cookiePolicy').count() == 0
    image = browser_client.request_security_code_img(page.content)
    assert Image.open(io.BytesIO(image.content)).size == (145, 55)
    assert len([call for call in calls if 'captcha' in call.url]) == 1
    result = browser_client.submit_booking_form(booking_params())
    assert 'BookingS2Form' in browser_client.form_actions
    assert b'QueryCode' in result.content
    posts = [call for call in calls if call.method == 'POST']
    assert len(posts) == 1
    data = parse_qs(posts[0].post_data)
    assert data['BookingS1Form:hf:0'] == ['session-token']
    assert data['homeCaptcha:securityCode'] == ['A7B3']
    assert data['toTimeInputField'] == ['2099/01/01']
    assert data['submitAction'] == ['search']


def test_unchecked_radio_does_not_trigger_change(browser_client):
    install_routes(browser_client)
    browser_client.request_booking_page()
    browser_client.page.evaluate("""() => {
        window.uncheckedChanges = 0;
        document.querySelector('input[value="radio20"]').addEventListener('change', () => {
            window.uncheckedChanges++;
        });
    }""")
    # Trap before actual submission to inspect events on this page.
    browser_client.page.locator('form').evaluate("""form => form.addEventListener('submit', event => {
        event.preventDefault();
        window.radioEvents = window.uncheckedChanges;
    })""")
    browser_client.page.set_default_timeout(250)
    params = booking_params()
    params['bookingMethod'] = 'radio19'
    with pytest.raises(RequestConnectionError):
        browser_client.submit_booking_form(params)
    assert browser_client.page.evaluate('window.radioEvents') == 0


def test_browser_does_not_repeat_failed_post(browser_client):
    calls = install_routes(browser_client, fail_post=True)
    browser_client.request_booking_page()
    with pytest.raises(RequestConnectionError):
        browser_client.submit_booking_form(booking_params())
    assert len([call for call in calls if call.method == 'POST']) == 1


def test_missing_required_field_does_not_submit(browser_client):
    calls = install_routes(browser_client)
    browser_client.request_booking_page()
    browser_client.page.locator('[name="homeCaptcha:securityCode"]').evaluate('el => el.remove()')
    with pytest.raises(ValueError):
        browser_client.submit_booking_form(booking_params())
    assert not any(call.method == 'POST' for call in calls)


def test_unattended_missing_form_never_prompts(browser_client, monkeypatch):
    def unexpected_input(*args):
        pytest.fail('自動模式不得等待輸入')
    monkeypatch.setattr('builtins.input', unexpected_input)
    browser_client.interactive = False
    browser_client.page.route('**/*', lambda route: route.fulfill(body='<html>Unavailable</html>'))
    with pytest.raises(ValueError, match='未取得訂票表單'):
        browser_client.request_booking_page()

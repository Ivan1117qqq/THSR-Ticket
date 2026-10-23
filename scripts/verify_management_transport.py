"""Real Chrome, synthetic pages, all network intercepted; never uses live booking data."""
import argparse
import base64
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from thsr_ticket.remote.browser_request import BrowserRequest
from thsr_ticket.remote.booking_management import BookingManagement
from thsr_ticket.storage_errors import StorageError

PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII='
CODE = '12345678'
TRIP = {'date': '2099-01-15', 'train_id': '0117', 'start_station': '台北', 'dest_station': '台中',
        'depart_time': '09:31'}


def detail(status='未付款'):
    return ('<!doctype html><meta charset="utf-8"><table>'
            '<tr><th>訂位代號</th><td>' + CODE + '</td></tr>'
            '<tr><th>付款狀態</th><td>' + status + '</td></tr></table>'
            '<table><tr><td>2099/01/15</td><td>台北</td><td>台中</td>'
            '<td>09:31</td><td>10:18</td><td>0117</td></tr></table>')


def button(label, action, confirm=False):
    handler = ' onsubmit="return confirm(\'您確定要取消此筆訂位嗎？\')"' if confirm else ''
    return f'<form method="post" action="{action}"{handler}><button type="submit">{label}</button></form>'


def verify(case):
    client = BrowserRequest(channel='chrome', headless=True, interactive=False, timeout=3)
    manager = BookingManagement(client)
    calls = []
    blocked = []

    def route(request_route):
        request = request_route.request
        parsed = urlparse(request.url)
        if parsed.hostname != 'irs.thsrc.com.tw':
            blocked.append(request.url)
            request_route.abort()
            return
        path = parsed.path
        calls.append((request.method, path))
        if path == '/captcha.png':
            request_route.fulfill(body=base64.b64decode(PNG), content_type='image/png')
            return
        if path == '/IMINT/':
            body = ('<!doctype html><meta charset="utf-8"><form id="HistoryForm" method="post"'
                    ' action="/IMINT/result"><input name="rocId"><input name="orderId">'
                    '<img id="HistoryForm_divCaptcha_passCode" src="/captcha.png?first">'
                    '<button id="HistoryForm_divCaptcha_reCodeLink" type="button"'
                    ' onclick="document.getElementById(\'HistoryForm_divCaptcha_passCode\').src=\'/captcha.png?next\'">'
                    '換圖</button><input name="divCaptcha:securityCode"><input type="submit" name="SubmitButton"></form>')
        elif path == '/IMINT/result':
            params = parse_qs(request.post_data or '')
            assert params['orderId'] == [CODE] and params['divCaptcha:securityCode'] == ['ABCD']
            body = detail('已付款' if case == 'paid' else '未付款')
            body += button('取消/修改訂位', '/IMINT/manage')
        elif path == '/IMINT/manage':
            body = detail() + button('取消訂位', 'https://outside.invalid/cancel' if case == 'foreign' else
                                     '/IMINT/confirm', confirm=True)
        elif path == '/IMINT/confirm':
            if case == 'disconnect':
                request_route.abort('connectionreset')
                return
            body = detail() + button('確認取消訂位', '/IMINT/cancelled')
        elif path == '/IMINT/cancelled':
            body = detail('已取消')
        else:
            raise AssertionError('Unexpected synthetic route')
        request_route.fulfill(body=body, content_type='text/html; charset=utf-8')

    try:
        client.context.route('**/*', route)
        image = manager.open('TEST-IDENTITY', CODE, TRIP)
        assert image.startswith('data:image/png;base64,')
        manager.refresh_captcha()
        snapshot = manager.query('ABCD')
        assert snapshot['trip_matches']
        if case == 'paid':
            try:
                manager.prepare_cancel()
            except StorageError:
                pass
            else:
                raise AssertionError('Paid booking was not blocked')
        elif case == 'foreign':
            try:
                manager.prepare_cancel()
            except ValueError:
                pass
            else:
                raise AssertionError('Foreign form action was not blocked')
        else:
            manager.prepare_cancel()
            if case == 'disconnect':
                try:
                    manager.cancel()
                except Exception:
                    pass
                else:
                    raise AssertionError('Disconnected cancellation was not reported')
                assert calls.count(('POST', '/IMINT/confirm')) == 1
                assert ('POST', '/IMINT/cancelled') not in calls
            else:
                assert manager.cancel()['status'] == 'cancelled'
                assert calls.count(('POST', '/IMINT/cancelled')) == 1
        assert not blocked  # Foreign action must be rejected before an outgoing request.
        return {'case': case, 'passed': True, 'intercepted_requests': len(calls)}
    finally:
        manager.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='build/management-transport.json')
    args = parser.parse_args()
    report = {'scope': 'real headless Chrome; synthetic official-origin routes; no live booking requests',
              'cases': [verify(case) for case in ('success', 'paid', 'foreign', 'disconnect')]}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

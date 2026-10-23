"""Attended official management session; exact semantic controls, no POST retries."""
import base64
import re
from urllib.parse import urljoin

from thsr_ticket.official_booking import HISTORY_URL, parse_official
from thsr_ticket.remote.browser_request import BrowserRequest
from thsr_ticket.remote.http_request import _site_url
from thsr_ticket.storage_errors import StorageError


class BookingManagement:
    def __init__(self, client=None):
        self.client = client or BrowserRequest(channel='chrome', interactive=False)
        self.page = self.client.page
        self.snapshot = None
        self.expected = {}
        self.code = ''

    def close(self):
        self.client.close()

    def read(self):
        _site_url(HISTORY_URL, self.page.url)
        return parse_official(self.page.content(), self.code, self.expected)

    def open(self, personal_id, code, expected):
        self.page.goto(HISTORY_URL, wait_until='domcontentloaded')
        _site_url(HISTORY_URL, self.page.url)
        notice = self.page.locator('#cookieAccpetBtn')
        if notice.is_visible():
            notice.click()
        form = self.page.locator('form#HistoryForm')
        if form.count() != 1:
            raise StorageError('official_unrecognized')
        _site_url(self.page.url, form.get_attribute('action') or self.page.url)
        form.locator('input[name="rocId"]').fill(personal_id)
        form.locator('input[name="orderId"]').fill(code)
        self.code, self.expected = code, expected
        return self.captcha()

    def captcha(self):
        _site_url(HISTORY_URL, self.page.url)
        image = self.page.locator('#HistoryForm_divCaptcha_passCode')
        image.wait_for(state='visible')
        self.page.wait_for_function("() => {const i=document.getElementById('HistoryForm_divCaptcha_passCode');"
                                    "return i && i.complete && i.naturalWidth>0;}")
        return 'data:image/png;base64,' + base64.b64encode(image.screenshot()).decode('ascii')

    def refresh_captcha(self):
        _site_url(HISTORY_URL, self.page.url)
        image = self.page.locator('#HistoryForm_divCaptcha_passCode')
        old = image.get_attribute('src')
        self.page.locator('#HistoryForm_divCaptcha_reCodeLink').click()
        self.page.wait_for_function("old => document.getElementById('HistoryForm_divCaptcha_passCode').src !== old",
                                    arg=urljoin(self.page.url, old or ''))
        return self.captcha()

    def query(self, captcha):
        if not re.fullmatch('[A-Za-z0-9]{4}', captcha):
            raise StorageError('official_captcha')
        _site_url(HISTORY_URL, self.page.url)
        form = self.page.locator('form#HistoryForm')
        _site_url(self.page.url, form.get_attribute('action') or self.page.url)
        if form.locator('input[name="orderId"]').input_value() != self.code:
            raise StorageError('official_mismatch')
        form.locator('input[name="divCaptcha:securityCode"]').fill(captcha)
        with self.page.expect_navigation(wait_until='domcontentloaded'):
            form.locator('input[type="submit"][name="SubmitButton"]').click()
        self.snapshot = self.read()
        return self.snapshot

    def exact_button(self, labels):
        _site_url(HISTORY_URL, self.page.url)
        controls = None
        for label in labels:
            candidates = self.page.get_by_role('button', name=label, exact=True).or_(
                self.page.get_by_role('link', name=label, exact=True))
            controls = candidates if controls is None else controls.or_(candidates)
        visible = [control for control in controls.all() if control.is_visible() and control.is_enabled()]
        if len(visible) != 1:
            raise StorageError('official_cancel_unavailable')
        target = visible[0]
        form_action = target.evaluate("el => el.form ? el.form.action : null")
        if form_action:
            _site_url(self.page.url, form_action)
        for attribute in ('href', 'formaction'):
            url = target.get_attribute(attribute)
            if url and not url.startswith('#'):
                _site_url(self.page.url, url)
        return target

    def prepare_cancel(self):
        snapshot = self.read()
        if snapshot['status'] != 'unpaid' or not snapshot['trip_matches']:
            raise StorageError('official_cancel_unavailable')
        # Official documentation identifies this as the management navigation, not final cancellation.
        control = self.exact_button(('取消/修改訂位', '取消／修改訂位'))
        with self.page.expect_navigation(wait_until='domcontentloaded'):
            control.click()
        fresh = self.read()
        if fresh['status'] != 'unpaid' or not fresh['trip_matches']:
            raise StorageError('official_mismatch')
        self.exact_button(('取消訂位',))
        return fresh

    def cancel(self):
        # Re-read immediately before submitting; do not trust the earlier review alone.
        fresh = self.read()
        if fresh['status'] != 'unpaid' or not fresh['trip_matches']:
            raise StorageError('official_mismatch')
        control = self.exact_button(('取消訂位',))

        def confirm_dialog(dialog):
            # The app already reviewed this exact unpaid booking and obtained explicit consent.
            known = (dialog.type == 'confirm' and len(dialog.message) < 180 and
                     re.fullmatch(r'.*(確定|確認).*(取消).*(訂位).*[?？。！!]?\s*', dialog.message, re.S))
            dialog.accept() if known else dialog.dismiss()
        self.page.once('dialog', confirm_dialog)
        with self.page.expect_navigation(wait_until='domcontentloaded'):
            control.click()
        self.page.remove_listener('dialog', confirm_dialog)
        result = self.read()
        if result['status'] == 'unpaid' and result['trip_matches']:
            final = self.exact_button(('確認取消訂位', '確認取消'))
            self.page.once('dialog', confirm_dialog)
            with self.page.expect_navigation(wait_until='domcontentloaded'):
                final.click()
            self.page.remove_listener('dialog', confirm_dialog)
            result = self.read()
        if result['status'] != 'cancelled':
            raise StorageError('official_unconfirmed')
        return result

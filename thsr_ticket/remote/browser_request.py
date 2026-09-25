"""Browser transport using a separate, temporary browser session."""
from typing import Any, Mapping
import time

from requests import ConnectionError as RequestConnectionError
from requests.models import Response

from thsr_ticket.configs.web.http_config import HTTPConfig
from thsr_ticket.remote.http_request import HTTPRequest, _site_url


class BrowserRequest(HTTPRequest):
    def __init__(self, channel: str = 'chrome', headless: bool = False, timeout: float = 30,
                 interactive: bool = True) -> None:
        try:
            from playwright.sync_api import sync_playwright, Error
        except ImportError as exc:
            raise RuntimeError('請先安裝 requirements-automation.txt 以使用瀏覽器模式。') from exc
        super().__init__(max_retries=0, timeout=timeout)
        self.browser = None
        self.driver = None
        self.native = None
        self.headless = headless
        self.interactive = interactive
        self.browser_error = Error
        try:
            self.driver = sync_playwright().start()
            if headless:
                self.browser = self.driver.chromium.launch(channel=channel, headless=True)
                self.context = self.browser.new_context(locale='zh-TW')
            else:
                from thsr_ticket.remote.native_browser import NativeBrowser
                self.native = NativeBrowser(channel)
                endpoint = self.native.start()
                deadline = time.monotonic() + min(timeout, 15)
                while True:
                    try:
                        self.browser = self.driver.chromium.connect_over_cdp(endpoint, timeout=1000)
                        break
                    except Error:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.2)
                self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.page.set_default_timeout(timeout * 1000)
            self.image_responses = {}
            self.page.on('response', self._remember_image)
        except (Error, OSError, RuntimeError) as exc:
            self.close()
            raise RuntimeError(f'無法啟動 {channel}，請確認已安裝該瀏覽器。') from exc

    def close(self) -> None:
        try:
            if self.browser is not None:
                self.browser.close()
        finally:
            try:
                if self.driver is not None:
                    self.driver.stop()
            finally:
                if self.native is not None:
                    self.native.close()
                super().close()

    def request_booking_page(self) -> Response:
        try:
            self.image_responses.clear()
            reply = self.page.goto(HTTPConfig.BOOKING_PAGE_URL, wait_until='domcontentloaded')
            cookie_notice = self.page.locator('#cookieAccpetBtn')
            if cookie_notice.is_visible():
                cookie_notice.click()
            result = self._snapshot(reply.status if reply else 200)
            if 'BookingS1Form' not in self.form_actions and not self.headless and self.interactive:
                input('瀏覽器未顯示訂票表單；請確認頁面或手動完成網站檢測後按 Enter（Ctrl+C 結束）：')
                result = self._snapshot()
            if 'BookingS1Form' not in self.form_actions:
                raise ValueError('瀏覽器未取得訂票表單；若顯示網站檢測，請在瀏覽器手動完成後再操作。')
            return result
        except self.browser_error as exc:
            raise RequestConnectionError('瀏覽器無法載入訂票首頁。') from exc

    def request_security_code_img(self, book_page: bytes) -> Response:
        try:
            # Capture the image already loaded by this session, avoiding a second captcha request.
            image = self.page.locator('#BookingS1Form_homeCaptcha_passCode')
            image.wait_for(state='visible')
            self.page.wait_for_function(
                "() => { const img = document.getElementById('BookingS1Form_homeCaptcha_passCode');"
                " return img && img.complete && img.naturalWidth > 0; }"
            )
            result = Response()
            result.status_code = 200
            result.url = _site_url(self.page.url, image.get_attribute('src'))
            original = self.image_responses.get(result.url)
            if original is None or not original.ok:
                raise ValueError('未取得原始驗證碼圖片，請重新查詢。')
            result.headers['Content-Type'] = original.headers.get('content-type', '')
            result._content = original.body()
            if not result.headers['Content-Type'].startswith('image/'):
                raise ValueError('驗證碼回應不是圖片。')
            return result
        except self.browser_error as exc:
            raise RequestConnectionError('瀏覽器未能取得驗證碼圖片。') from exc

    def _remember_image(self, response: Any) -> None:
        if response.request.resource_type == 'image':
            self.image_responses[response.url] = response

    def _snapshot(self, status: int = 200) -> Response:
        _site_url(HTTPConfig.BASE_URL, self.page.url)
        result = Response()
        result.status_code = status
        result.url = self.page.url
        result.encoding = 'utf-8'
        result.headers['Content-Type'] = 'text/html; charset=utf-8'
        result._content = self.page.content().encode('utf-8')
        result.raise_for_status()
        self._remember_forms(result)
        return result

    def _submit(self, form_id: str, params: Mapping[str, Any]) -> Response:
        if form_id not in self.form_actions:
            raise ValueError(f'找不到訂票表單 {form_id}，請重新查詢。')
        required = {
            'BookingS1Form': ['selectStartStation', 'selectDestinationStation', 'toTimeInputField',
                              'toTimeTable', 'homeCaptcha:securityCode'],
            'BookingS2Form': ['TrainQueryDataViewPanel:TrainGroup'],
            'BookingS3FormSP': ['dummyId', 'dummyPhone'],
        }[form_id]
        try:
            form = self.page.locator(f'form[id="{form_id}"]')
            # Validate origin again in case the page changed since its snapshot.
            _site_url(self.page.url, form.get_attribute('action') or self.page.url)
            for name, value in params.items():
                if value is None:
                    continue
                fields = form.locator(f'[name="{name}"]')
                if not fields.count():
                    if name in required:
                        raise ValueError(f'找不到必要欄位 {name}。')
                    continue
                field = fields.first
                kind = field.get_attribute('type')
                tag = field.evaluate('el => el.tagName.toLowerCase()')
                if kind == 'hidden':
                    if name in ('toTimeInputField', 'backTimeInputField'):
                        field.evaluate("""(el, value) => {
                            if (el._flatpickr) el._flatpickr.setDate(value, true, 'Y/m/d');
                            else el.value = value;
                        }""", str(value))
                elif tag == 'select':
                    if field.input_value() != str(value):
                        field.select_option(str(value))
                elif kind == 'radio':
                    for option in fields.all():
                        if option.get_attribute('value') == str(value):
                            option.check()
                            break
                    else:
                        raise ValueError(f'找不到欄位 {name} 的選項。')
                elif kind == 'checkbox':
                    field.set_checked(str(value) == 'on')
                elif field.is_visible() or value != '':
                    field.fill(str(value))
            if not form.evaluate('form => form.checkValidity()'):
                raise ValueError('網站表單驗證未通過，請檢查填寫內容。')
            with self.page.expect_navigation(wait_until='domcontentloaded') as navigation:
                submit = form.locator('input[type="submit"]:visible, button[type="submit"]:visible')
                if submit.count():
                    submit.first.click()
                else:
                    form.evaluate('form => form.requestSubmit()')
            reply = navigation.value
            return self._snapshot(reply.status if reply else 200)
        except self.browser_error as exc:
            # Never repeat a POST, including a navigation timeout after a successful submission.
            raise RequestConnectionError('瀏覽器表單操作失敗；若已送出訂票，請先確認訂位狀態。') from exc

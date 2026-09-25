from typing import Mapping, Any
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from requests.models import Response
from bs4 import BeautifulSoup
from urllib3.util.retry import Retry

from thsr_ticket.configs.web.http_config import HTTPConfig
from thsr_ticket.configs.web.parse_html_element import BOOKING_PAGE


class HTTPRequest:
    def __init__(self, max_retries: int = 3, timeout: float = 20) -> None:
        self.sess = requests.Session()
        self.timeout = timeout
        self.form_actions: dict = {}
        self.hidden_fields: dict = {}
        retries = Retry(total=max_retries, connect=0, read=max_retries,
                        status=0, other=0, allowed_methods=frozenset({'GET'}))
        self.sess.mount("https://", HTTPAdapter(max_retries=retries))

        self.common_head_html: dict = {
            "Host": HTTPConfig.HTTPHeader.BOOKING_PAGE_HOST,
            "User-Agent": HTTPConfig.HTTPHeader.USER_AGENT,
            "Accept": HTTPConfig.HTTPHeader.ACCEPT_HTML,
            "Accept-Language": HTTPConfig.HTTPHeader.ACCEPT_LANGUAGE,
            "Accept-Encoding": HTTPConfig.HTTPHeader.ACCEPT_ENCODING
        }

    def request_booking_page(self) -> Response:
        return self._request('GET', HTTPConfig.BOOKING_PAGE_URL)

    def close(self) -> None:
        self.sess.close()

    def request_security_code_img(self, book_page: bytes) -> Response:
        img_url = parse_security_img_url(book_page)
        return self._request('GET', img_url)

    def submit_booking_form(self, params: Mapping[str, Any]) -> Response:
        return self._submit('BookingS1Form', params)

    def submit_train(self, params: Mapping[str, Any]) -> Response:
        return self._submit('BookingS2Form', params)

    def submit_ticket(self, params: Mapping[str, Any]) -> Response:
        return self._submit('BookingS3FormSP', params)

    def _submit(self, form_id: str, params: Mapping[str, Any]) -> Response:
        if form_id not in self.form_actions:
            raise ValueError(f'找不到訂票表單 {form_id}，請重新查詢。')
        data = {key: value for key, value in params.items() if value is not None}
        data.update(self.hidden_fields.get(form_id, {}))
        for name in ('toTimeInputField', 'backTimeInputField'):
            if params.get(name) is not None:
                data[name] = params[name]
        return self._request('POST', self.form_actions[form_id], data=data)

    def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        response = self.sess.request(
            method, url, headers=self.common_head_html, timeout=self.timeout,
            allow_redirects=True, **kwargs
        )
        response.raise_for_status()
        if 'image/' not in response.headers.get('Content-Type', ''):
            self._remember_forms(response)
        return response

    def _remember_forms(self, response: Response) -> None:
        page = BeautifulSoup(response.content, features='html.parser')
        self.form_actions = {}
        self.hidden_fields = {}
        for form in page.find_all('form', id=True, action=True):
            target = _site_url(response.url, str(form['action']))
            self.form_actions[form['id']] = target
            self.hidden_fields[form['id']] = {
                field['name']: field.get('value', '')
                for field in form.find_all('input', type='hidden', attrs={'name': True})
            }


def _site_url(base: str, target: str) -> str:
    url = urljoin(base, target)
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != urlparse(HTTPConfig.BASE_URL).netloc:
        raise ValueError('訂票頁面包含非預期的網址。')
    return url


def parse_security_img_url(html: bytes) -> str:
    page = BeautifulSoup(html, features="html.parser")
    element = page.find(**BOOKING_PAGE["security_code_img"])
    if element is None or not element.get('src'):
        raise ValueError('找不到驗證碼圖片，網站頁面可能已變更或連線已失效。')
    return _site_url(HTTPConfig.BOOKING_PAGE_URL, element['src'])

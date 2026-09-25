import io
import json
from PIL import Image
from typing import Tuple
from datetime import date

from bs4 import BeautifulSoup
from requests.models import Response
from pydantic import ValidationError

from thsr_ticket.model.db import Record
from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.configs.web.param_schema import BookingModel
from thsr_ticket.configs.web.parse_html_element import BOOKING_PAGE
from thsr_ticket.configs.web.enums import StationMapping, TicketType
from thsr_ticket.view.input_utils import read_int
from thsr_ticket.captcha import CaptchaReader
from thsr_ticket.configs.common import (
    AVAILABLE_TIME_TABLE,
    MAX_TICKET_NUM,
)


class FirstPageFlow:
    def __init__(self, client: HTTPRequest, record: Record = None, captcha_reader: CaptchaReader = None) -> None:
        self.client = client
        self.record = record
        self.captcha_reader = captcha_reader
        self.used_ocr = False

    def run(self) -> Tuple[Response, BookingModel]:
        # First page. Booking options
        print('請稍等...')
        book_page = self.client.request_booking_page().content
        img_resp = self.client.request_security_code_img(book_page).content
        page = BeautifulSoup(book_page, features='html.parser')

        while True:
            try:
                book_model = BookingModel(
                    start_station=self.select_station('啟程'),
                    dest_station=self.select_station('到達', default_value=StationMapping.Zuouing.value),
                    outbound_date=self.select_date('出發'),
                    outbound_time=self.select_time('啟程'),
                    adult_ticket_num=self.select_ticket_num(TicketType.ADULT),
                    child_ticket_num=self.select_ticket_num(TicketType.CHILD, 0),
                    disabled_ticket_num=self.select_ticket_num(TicketType.DISABLED, 0),
                    elder_ticket_num=self.select_ticket_num(TicketType.ELDER, 0),
                    college_ticket_num=self.select_ticket_num(TicketType.COLLEGE, 0),
                    class_type=read_int('車廂：0 標準 / 1 商務（預設 0）：', 0, 1, 0),
                    seat_prefer=_select_seat_prefer(page),
                    types_of_trip=_parse_types_of_trip_value(page),
                    search_by=_parse_search_by(page),
                    security_code=self.read_security_code(img_resp),
                )
                break
            except ValidationError as exc:
                print('資料不正確：' + '；'.join(error['msg'] for error in exc.errors()))
                self.record = None
        json_params = book_model.json(by_alias=True)
        dict_params = json.loads(json_params)
        resp = self.client.submit_booking_form(dict_params)
        return resp, book_model

    def read_security_code(self, image: bytes) -> str:
        self.used_ocr = False
        if self.captcha_reader is not None:
            guess = self.captcha_reader.recognize(image)
            if guess is not None:
                self.used_ocr = True
                print(f'已自動辨識驗證碼：{guess.text}')
                return guess.text
            print('自動辨識不可用或結果不確定，請手動輸入。')
        return _input_security_code(image)

    def select_station(self, travel_type: str, default_value: int = StationMapping.Taipei.value) -> int:
        if (
            self.record
            and (
                station := {
                    '啟程': self.record.start_station,
                    '到達': self.record.dest_station,
                }.get(travel_type)
            )
        ):
            return station

        print(f'選擇{travel_type}站：')
        for station in StationMapping:
            print(f'{station.value}. {station.name}')

        return read_int(f'輸入選擇（預設 {default_value}）：', 1, 12, default_value)

    def select_date(self, date_type: str) -> str:
        today = date.today()
        while True:
            value = input(f'選擇{date_type}日期（YYYY-MM-DD，預設 {today}）：').strip() or str(today)
            try:
                return BookingModel.check_date(value)
            except ValueError:
                print('請輸入有效日期，且不得早於今天；可訂日期以網站回覆為準。')

    def select_time(self, time_type: str, default_value: int = 10) -> str:
        if self.record and (
            time_str := {
                '啟程': self.record.outbound_time,
                '回程': None,
            }.get(time_type)
        ):
            return time_str

        print('選擇出發時間：')
        for idx, t_str in enumerate(AVAILABLE_TIME_TABLE):
            t_int = int(t_str[:-1])
            if t_str[-1] == "A" and (t_int // 100) == 12:
                t_int = "{:04d}".format(t_int % 1200)  # type: ignore
            elif t_int != 1230 and t_str[-1] == "P":
                t_int += 1200
            t_str = str(t_int)
            print(f'{idx+1}. {t_str[:-2]}:{t_str[-2:]}')

        selected_opt = read_int(f'輸入選擇（預設：{default_value}）：', 1, len(AVAILABLE_TIME_TABLE), default_value)
        return AVAILABLE_TIME_TABLE[selected_opt-1]

    def select_ticket_num(self, ticket_type: TicketType, default_ticket_num: int = 1) -> str:
        if self.record and (
            ticket_num_str := {
                TicketType.ADULT: self.record.adult_num,
                TicketType.CHILD: None,
                TicketType.DISABLED: None,
                TicketType.ELDER: None,
                TicketType.COLLEGE: None,
            }.get(ticket_type)
        ):
            return ticket_num_str

        ticket_type_name = {
            TicketType.ADULT: '成人',
            TicketType.CHILD: '孩童',
            TicketType.DISABLED: '愛心',
            TicketType.ELDER: '敬老',
            TicketType.COLLEGE: '大學生',
        }.get(ticket_type)

        print(f'選擇{ticket_type_name}票數（0~{MAX_TICKET_NUM}）（預設：{default_ticket_num}）')
        ticket_num = read_int('票數：', 0, MAX_TICKET_NUM, default_ticket_num)
        return f'{ticket_num}{ticket_type.value}'


def _parse_seat_prefer_value(page: BeautifulSoup) -> str:
    options = page.find(**BOOKING_PAGE["seat_prefer_radio"])
    if options is None:
        raise ValueError('找不到座位偏好選項，網站頁面可能已變更。')
    preferred_seat = options.find('option', selected=True) or options.find('option')
    if preferred_seat is None:
        raise ValueError('找不到座位偏好選項。')
    return preferred_seat.attrs['value']


def _select_seat_prefer(page: BeautifulSoup) -> str:
    default = _parse_seat_prefer_value(page)
    options = page.find(**BOOKING_PAGE['seat_prefer_radio']).find_all('option', value=True)
    for idx, option in enumerate(options, 1):
        print(f'{idx}. {option.get_text(strip=True)}')
    default_idx = next(idx for idx, option in enumerate(options, 1) if option['value'] == default)
    selected = read_int(f'座位偏好（預設 {default_idx}）：', 1, len(options), default_idx)
    return options[selected - 1]['value']


def _parse_types_of_trip_value(page: BeautifulSoup) -> int:
    options = page.find(**BOOKING_PAGE["types_of_trip"])
    if options is None or options.find('option', value='0') is None:
        raise ValueError('找不到單程訂票選項，網站頁面可能已變更。')
    return 0


def _parse_search_by(page: BeautifulSoup) -> str:
    candidates = page.find_all('input', {'name': 'bookingMethod'})
    tag = next((cand for cand in candidates if 'checked' in cand.attrs), None)
    if tag is None:
        raise ValueError('找不到車次查詢方式，網站頁面可能已變更。')
    return tag.attrs['value']


def _input_security_code(img_resp: bytes) -> str:
    print('輸入驗證碼：')
    image = Image.open(io.BytesIO(img_resp))
    image.show()
    while True:
        code = input().strip()
        if code:
            return code
        print('請輸入圖片中的驗證碼。')

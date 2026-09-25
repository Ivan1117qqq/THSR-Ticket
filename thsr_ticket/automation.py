"""Scheduled, sequential booking with no interactive prompts or final POST retries."""
import json
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, root_validator, validator

from thsr_ticket.configs.web.param_schema import BookingModel, ConfirmTicketModel, ConfirmTrainModel
from thsr_ticket.controller.first_page_flow import (
    _parse_search_by, _parse_seat_prefer_value, _parse_types_of_trip_value,
)
from thsr_ticket.controller.confirm_ticket_flow import _parse_member_radio
from thsr_ticket.view_model.avail_trains import AvailTrains
from thsr_ticket.view_model.booking_result import BookingResult
from thsr_ticket.view_model.error_feedback import ErrorFeedback
from thsr_ticket.view.web.show_booking_result import ShowBookingResult


TAIPEI = timezone(timedelta(hours=8))


def clock_time(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise ValueError('時間必須為 HH:MM。')
    return value


def query_time(value):
    hour, minute = map(int, value.split(':'))
    minute = (minute // 30) * 30
    if 1 <= hour < 6:
        return '1230A'
    if hour == 0 and minute == 0:
        return '1201A'
    if hour == 12 and minute == 0:
        return '1200N'
    return f'{hour % 12 or 12}{minute:02d}{"A" if hour < 12 else "P"}'


class AutomationConfig(BaseModel):
    start_at: datetime
    interval_seconds: float = 1.0
    max_attempts: int = Field(60, ge=1, le=10000)
    start_station: int
    dest_station: int
    outbound_date: str
    earliest_departure: str = '09:30'
    latest_departure: str = '23:59'
    train_ids: List[int] = Field(default_factory=list)
    adult_tickets: int = Field(1, ge=0, le=10)
    child_tickets: int = Field(0, ge=0, le=10)
    disabled_tickets: int = Field(0, ge=0, le=10)
    elder_tickets: int = Field(0, ge=0, le=10)
    college_tickets: int = Field(0, ge=0, le=10)
    class_type: int = 0
    personal_id: str = Field(..., repr=False)
    phone_num: str = Field('', repr=False)

    class Config:
        extra = 'forbid'

    @validator('start_at')
    def local_time(cls, value):
        return value.replace(tzinfo=TAIPEI) if value.tzinfo is None else value.astimezone(TAIPEI)

    @validator('interval_seconds')
    def positive_interval(cls, value):
        if not math.isfinite(value) or value <= 0:
            raise ValueError('查詢間隔必須是大於 0 的有限秒數。')
        return value

    _times = validator('earliest_departure', 'latest_departure', allow_reuse=True)(clock_time)

    @validator('train_ids')
    def positive_ids(cls, value):
        if any(number <= 0 for number in value) or len(set(value)) != len(value):
            raise ValueError('車次必須是正整數且不得重複。')
        return value

    @root_validator(skip_on_failure=True)
    def validate_models(cls, values):
        if values['earliest_departure'] > values['latest_departure']:
            raise ValueError('最晚出發時間不得早於最早出發時間。')
        if values['start_at'].date() > datetime.strptime(
                BookingModel.check_date(values['outbound_date']), '%Y/%m/%d').date():
            raise ValueError('啟動日期不得晚於乘車日期。')
        cls.build_booking(values, 'radio1', 'radio1', 'TEST')
        ticket = ConfirmTicketModel(personal_id=values['personal_id'], phone_num=values['phone_num'],
                                    member_radio='radio1')
        values.update(personal_id=ticket.personal_id, phone_num=ticket.phone_num)
        return values

    @staticmethod
    def build_booking(values, search_by, seat_prefer, code):
        counts = {f'{name}_ticket_num': f'{values[name + "_tickets"]}{suffix}'
                  for name, suffix in zip(('adult', 'child', 'disabled', 'elder', 'college'), 'FHWEP')}
        return BookingModel(
            start_station=values['start_station'], dest_station=values['dest_station'],
            outbound_date=values['outbound_date'], outbound_time=query_time(values['earliest_departure']),
            class_type=values['class_type'], search_by=search_by, types_of_trip=0,
            seat_prefer=seat_prefer, security_code=code, **counts,
        )

    @classmethod
    def load(cls, path):
        return cls.parse_obj(json.loads(Path(path).read_text(encoding='utf-8-sig')))

    def select(self, trains):
        candidates = [train for train in trains
                      if self.earliest_departure <= clock_time(train.depart.strip()) <= self.latest_departure
                      and (not self.train_ids or train.id in self.train_ids)]
        if not candidates:
            return None
        return min(candidates, key=lambda train: (
            self.train_ids.index(train.id) if self.train_ids else 0, train.depart, train.id))


def wait_until(target, now=lambda: datetime.now(TAIPEI), sleep=time.sleep):
    while True:
        remaining = (target - now()).total_seconds()
        if remaining <= 0:
            return
        sleep(min(remaining, 30))


def check_errors(response):
    response.raise_for_status()
    errors = ErrorFeedback().parse(response.content)
    if errors:
        raise RuntimeError('網站拒絕本次操作，已停止：' + '；'.join(error.msg for error in errors))


def no_seats_response(response):
    response.raise_for_status()
    errors = ErrorFeedback().parse(response.content)
    known_messages = ('查無符合條件之車次', '查無符合條件的車次', '所選時段已無剩餘座位')
    return bool(errors) and all(any(message in error.msg for message in known_messages) for error in errors)


class AutomationRunner:
    def __init__(self, config, client, reader, state_path, sleep=time.sleep):
        self.config, self.client, self.reader = config, client, reader
        self.state_path = Path(state_path)
        self.sleep = sleep

    def run(self, query_only=False):
        if not query_only and self.state_path.exists():
            raise RuntimeError(f'已有訂位送出紀錄，請先確認訂位狀態：{self.state_path}')
        for attempt in range(1, self.config.max_attempts + 1):
            print(f'第 {attempt}/{self.config.max_attempts} 次查詢。')
            first = self.client.request_booking_page()
            check_errors(first)
            page = BeautifulSoup(first.content, 'html.parser')
            _parse_types_of_trip_value(page)
            image = self.client.request_security_code_img(first.content)
            image.raise_for_status()
            guess = self.reader.recognize(image.content)
            if guess is None:
                raise RuntimeError('驗證碼無可靠辨識結果；自動模式已停止，未送出訂位。')
            model = self.config.build_booking(self.config.dict(), _parse_search_by(page),
                                              _parse_seat_prefer_value(page), guess.text)
            reply = self.client.submit_booking_form(json.loads(model.json(by_alias=True)))
            selected = None
            if not no_seats_response(reply):
                check_errors(reply)
                # An unexpected page is not evidence of sold-out trains.
                result_page = BeautifulSoup(reply.content, 'html.parser')
                if result_page.find('form', id='BookingS2Form') is None:
                    raise RuntimeError('查詢未回傳車次表單，已停止；請確認網站狀態。')
                selected = self.config.select(AvailTrains().parse(reply.content))
            if selected is not None:
                print(f'符合條件：{selected.id:04d}，{selected.depart} → {selected.arrive}')
                if query_only:
                    print('僅查詢模式結束，未送出訂位。')
                    return True
                self.book(selected)
                return True
            if attempt < self.config.max_attempts:
                print(f'沒有符合條件的車次，{self.config.interval_seconds:g} 秒後重查。')
                self.sleep(self.config.interval_seconds)
        print('已達查詢次數上限，未送出訂位。')
        return False

    def book(self, selected):
        train = ConfirmTrainModel(selected_train=selected.form_value)
        response = self.client.submit_train(json.loads(train.json(by_alias=True)))
        check_errors(response)
        page = BeautifulSoup(response.content, 'html.parser')
        model = ConfirmTicketModel(personal_id=self.config.personal_id, phone_num=self.config.phone_num,
                                   member_radio=_parse_member_radio(page))
        # Exclusive creation prevents two processes using this config from submitting twice.
        # Keep this marker even if the POST, parsing, or process fails afterwards.
        with self.state_path.open('x', encoding='utf-8') as handle:
            json.dump({'status': 'submission_pending', 'train_id': selected.id}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            result = self.client.submit_ticket(json.loads(model.json(by_alias=True)))
            check_errors(result)
            tickets = BookingResult().parse(result.content)
            if not tickets or any(not ticket.id.strip() for ticket in tickets):
                raise ValueError('缺少訂位代碼。')
        except Exception as exc:
            raise RuntimeError('訂位已嘗試送出，結果尚未確認；請至官網確認，勿直接重跑。') from exc
        self.state_path.write_text(json.dumps(
            {'status': 'booked', 'booking_codes': [ticket.id for ticket in tickets]}, ensure_ascii=False),
            encoding='utf-8')
        ShowBookingResult().show(tickets)
        print('訂位成功，已停止；尚未付款。')

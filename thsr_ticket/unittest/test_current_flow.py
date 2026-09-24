from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from bs4 import BeautifulSoup
from pydantic import ValidationError

from thsr_ticket.configs.web.param_schema import BookingModel, ConfirmTicketModel
from thsr_ticket.controller.booking_flow import BookingFlow
from thsr_ticket.controller.confirm_train_flow import ConfirmTrainFlow
from thsr_ticket.controller.first_page_flow import _parse_seat_prefer_value, _parse_search_by
from thsr_ticket.model.db import ParamDB
from thsr_ticket.remote.http_request import HTTPRequest, parse_security_img_url
from thsr_ticket.view.input_utils import read_int, mask_private
from thsr_ticket.view_model.avail_trains import AvailTrains
from thsr_ticket.view_model.booking_result import BookingResult
from thsr_ticket.view_model.error_feedback import ErrorFeedback


FIXTURES = Path(__file__).parent / 'fixtures'


def html(name):
    return (FIXTURES / f'{name}.html').read_bytes()


def response(content, content_type='text/html', status=200):
    result = requests.Response()
    result._content = content
    result.status_code = status
    result.url = 'https://irs.thsrc.com.tw/IMINT/'
    result.headers['Content-Type'] = content_type
    return result


@pytest.fixture
def booking_data():
    return dict(start_station=2, dest_station=12, search_by='radio19', types_of_trip=0,
                outbound_date=str(date.today()), outbound_time='930A', security_code='ABCD',
                seat_prefer='radio17')


@pytest.mark.parametrize('field,value', [
    ('adult_ticket_num', '11F'), ('adult_ticket_num', '1Fjunk'),
    ('adult_ticket_num', '-1F'), ('adult_ticket_num', '1H'),
    ('child_ticket_num', '12H'), ('dest_station', 2), ('start_station', 13),
    ('search_by', 'radio1junk'), ('class_type', 3),
    ('outbound_date', str(date.today() - timedelta(days=1))),
])
def test_booking_validation(booking_data, field, value):
    booking_data[field] = value
    with pytest.raises(ValidationError):
        BookingModel(**booking_data)


def test_total_tickets_and_serialization(booking_data):
    with pytest.raises(ValidationError):
        BookingModel(**booking_data, adult_ticket_num='0F')
    with pytest.raises(ValidationError):
        BookingModel(**booking_data, adult_ticket_num='10F', child_ticket_num='1H')
    model = BookingModel(**booking_data, adult_ticket_num='2F', child_ticket_num='1H')
    assert model.dict(by_alias=True)['ticketPanel:rows:1:ticketAmount'] == '1H'
    assert model.outbound_date == date.today().strftime('%Y/%m/%d')


@pytest.mark.parametrize('field,value', [('personal_id', 'invalid'), ('phone_num', '0812345678'),
                                         ('phone_num', '09abcdefgh')])
def test_ticket_validation(field, value):
    data = dict(personal_id='A123456789', phone_num='', member_radio='radio1')
    data[field] = value
    with pytest.raises(ValidationError):
        ConfirmTicketModel(**data)


def test_database_roundtrip(tmp_path, monkeypatch, booking_data):
    monkeypatch.chdir(tmp_path)
    book = BookingModel(**booking_data)
    ticket = ConfirmTicketModel(personal_id='A123456789', phone_num='', member_radio='radio1')
    for path in ('history.json', str(tmp_path / 'nested' / 'history.json')):
        db = ParamDB(path)
        assert db.get_history() == []
        db.save(book, ticket)
        db.save(book, ticket)
        assert len(db.get_history()) == 1
        assert db.get_history()[0].personal_id == ticket.personal_id


def test_parser_contracts():
    page = BeautifulSoup(html('booking'), 'html.parser')
    assert _parse_seat_prefer_value(page) == 'radio17'
    assert _parse_search_by(page) == 'radio19'
    assert parse_security_img_url(html('booking')) == 'https://irs.thsrc.com.tw/IMINT/captcha?id=example'
    parser = AvailTrains()
    for _ in range(2):
        trains = parser.parse(html('trains'))
        assert len(trains) == 1
        assert trains[0].id == 615
        assert trains[0].discount_str == '(65折)'
    ticket = BookingResult().parse(html('result'))[0]
    assert ticket.id == 'TEST1234'
    assert ticket.start_station == '台北'
    assert ticket.payment_deadline == '2099/01/02'


def test_missing_page_elements():
    for parse in (parse_security_img_url, BookingResult().parse):
        with pytest.raises(ValueError):
            parse(b'<html></html>')
    with pytest.raises(ValueError):
        AvailTrains().parse(b'<label class="result-item"></label>')


def test_error_parser_does_not_retain_old_errors():
    parser = ErrorFeedback()
    assert len(parser.parse(b'<span class="feedbackPanelERROR">bad captcha</span>')) == 1
    assert parser.parse(b'<html></html>') == []


def test_invalid_menu_values_retry(monkeypatch):
    entries = iter(['abc', '-1', '4', '2'])
    monkeypatch.setattr('builtins.input', lambda _: next(entries))
    assert read_int('choice', 1, 3, 1) == 2
    assert mask_private('A123456789') == '*******789'


def test_requery_does_not_submit_train(monkeypatch):
    monkeypatch.setattr('builtins.input', lambda _: '0')
    client = Mock()
    _, selected = ConfirmTrainFlow(client, response(html('trains'))).run()
    assert selected is None
    client.submit_train.assert_not_called()


def test_http_forms_timeout_and_body():
    client = HTTPRequest(timeout=7)
    client.sess.request = Mock(side_effect=[response(html('booking')), response(b'image', 'image/png'),
                                            response(html('trains'))])
    client.request_booking_page()
    client.request_security_code_img(html('booking'))
    client.submit_booking_form({'BookingS1Form:hf:0': '', 'dummyId': 'example', 'unused': None})
    args, kwargs = client.sess.request.call_args
    assert args == ('POST', 'https://irs.thsrc.com.tw/IMINT/?step=booking')
    assert kwargs['timeout'] == 7
    assert kwargs['data'] == {'BookingS1Form:hf:0': 'session-token', 'dummyId': 'example'}
    assert 'params' not in kwargs
    retry = client.sess.get_adapter('https://').max_retries
    assert 'POST' not in retry.allowed_methods
    assert retry.connect == 0


def test_http_errors_and_unexpected_action():
    client = HTTPRequest()
    client.sess.request = Mock(return_value=response(b'failure', status=503))
    with pytest.raises(requests.HTTPError):
        client.request_booking_page()
    client.sess.request.return_value = response(b'<form id="BookingS1Form" action="https://example.org/">')
    with pytest.raises(ValueError):
        client.request_booking_page()


def test_full_flow_offline(monkeypatch, tmp_path):
    client = HTTPRequest()
    client.sess.request = Mock(side_effect=[response(html('booking')), response(b'img', 'image/png'),
                                            response(html('trains')), response(html('confirmation')),
                                            response(html('result'))])
    monkeypatch.setattr('thsr_ticket.controller.booking_flow.HTTPRequest', lambda: client)
    monkeypatch.setattr('thsr_ticket.controller.booking_flow.ParamDB', lambda: ParamDB(str(tmp_path / 'history.json')))
    monkeypatch.setattr('thsr_ticket.controller.first_page_flow._input_security_code', lambda _: 'ABCD')
    # Stations, date, time, five ticket counts, class, seat, train, ID, phone, save.
    entries = iter([''] * 12 + ['A123456789', '', '0'])
    monkeypatch.setattr('builtins.input', lambda *args: next(entries))
    flow = BookingFlow()
    result = flow.run()
    assert result.content == html('result')
    calls = client.sess.request.call_args_list
    assert [call.args[0] for call in calls] == ['GET', 'GET', 'POST', 'POST', 'POST']
    assert calls[-1].kwargs['data']['dummyId'] == 'A123456789'
    assert flow.db.get_history() == []


@pytest.mark.parametrize('retry_reason', ['captcha', 'no_trains', 'requery'])
def test_retry_flow_offline(monkeypatch, tmp_path, retry_reason):
    first_result = {
        'captcha': b'<span class="feedbackPanelERROR">invalid captcha</span>',
        'no_trains': b'<html></html>',
        'requery': html('trains'),
    }[retry_reason]
    client = HTTPRequest()
    client.sess.request = Mock(side_effect=[
        response(html('booking')), response(b'img', 'image/png'), response(first_result),
        response(html('booking')), response(b'img', 'image/png'), response(html('trains')),
        response(html('confirmation')), response(html('result')),
    ])
    monkeypatch.setattr('thsr_ticket.controller.booking_flow.HTTPRequest', lambda: client)
    monkeypatch.setattr('thsr_ticket.controller.booking_flow.ParamDB', lambda: ParamDB(str(tmp_path / 'history.json')))
    monkeypatch.setattr('thsr_ticket.controller.first_page_flow._input_security_code', lambda _: 'ABCD')
    entries = iter([''] * 11 + [('0' if retry_reason == 'requery' else '1')]
                   + [''] * 12 + ['A123456789', '', '0'])
    monkeypatch.setattr('builtins.input', lambda *args: next(entries))
    assert BookingFlow().run().content == html('result')
    final_posts = [call for call in client.sess.request.call_args_list if 'step=ticket' in call.args[1]]
    assert len(final_posts) == 1


@pytest.mark.parametrize('final_response', [requests.Timeout(), response(b'<html>unexpected</html>')])
def test_final_submission_is_not_repeated(monkeypatch, tmp_path, final_response):
    client = HTTPRequest()
    client.sess.request = Mock(side_effect=[response(html('booking')), response(b'img', 'image/png'),
                                            response(html('trains')), response(html('confirmation')),
                                            final_response])
    monkeypatch.setattr('thsr_ticket.controller.booking_flow.HTTPRequest', lambda: client)
    monkeypatch.setattr('thsr_ticket.controller.booking_flow.ParamDB', lambda: ParamDB(str(tmp_path / 'history.json')))
    monkeypatch.setattr('thsr_ticket.controller.first_page_flow._input_security_code', lambda _: 'ABCD')
    entries = iter([''] * 12 + ['A123456789', ''])
    monkeypatch.setattr('builtins.input', lambda *args: next(entries))
    if isinstance(final_response, requests.Timeout):
        with pytest.raises(requests.Timeout):
            BookingFlow().run()
    else:
        BookingFlow().run()
    assert client.sess.request.call_count == 5

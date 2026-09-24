import pytest
from bs4 import BeautifulSoup

from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.controller.first_page_flow import (
    _parse_seat_prefer_value, _parse_types_of_trip_value, _parse_search_by,
)


@pytest.mark.integration
def test_requests_work():
    client = HTTPRequest(max_retries=0, timeout=10)

    resp = client.request_booking_page()
    assert resp.status_code == 200
    assert 'BookingS1Form' in client.form_actions
    page = BeautifulSoup(resp.content, 'html.parser')
    assert _parse_seat_prefer_value(page)
    assert _parse_types_of_trip_value(page) == 0
    assert _parse_search_by(page)
    image = client.request_security_code_img(resp.content)
    assert image.status_code == 200
    assert image.headers.get('Content-Type', '').startswith('image/')

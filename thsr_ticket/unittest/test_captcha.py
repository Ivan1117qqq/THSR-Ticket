from unittest.mock import Mock

import pytest

from thsr_ticket.captcha import CaptchaGuess, CaptchaReader, decode_prediction
from thsr_ticket.controller.first_page_flow import FirstPageFlow
from thsr_ticket.controller.booking_flow import BookingFlow
from thsr_ticket.model.db import ParamDB
from thsr_ticket.main import check_connection
from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.unittest.test_current_flow import html, response


def prediction(indices=(1, 0, 2, 0, 3, 0, 4), score=0.98):
    rows = []
    for index in indices:
        confidence = 0.999 if index == 0 else score
        row = [(1 - confidence) / 4] * 5
        row[index] = confidence
        rows.append([row])
    return {'charset': ['', 'A', '7', 'b', '3'], 'probabilities': rows}


def test_ctc_decoding_and_repeated_letters():
    assert decode_prediction(prediction()).text == 'A7B3'
    assert decode_prediction(prediction((1, 1, 0, 1, 2, 3))).text == 'AA7B'
    assert decode_prediction(prediction((1, 1, 2, 3))) is None  # Only three decoded characters.


def test_both_model_array_layouts():
    data = prediction()
    data['probabilities'] = [[frame[0] for frame in data['probabilities']]]
    assert decode_prediction(data).text == 'A7B3'


def test_case_variants_are_combined():
    data = {'charset': ['', 'A', 'a', '7', 'B', '3'], 'probabilities': [
        [0.01, 0.45, 0.50, 0.01, 0.01, 0.02],
        [0.01, 0.01, 0.01, 0.95, 0.01, 0.01],
        [0.01, 0.01, 0.01, 0.01, 0.95, 0.01],
        [0.01, 0.01, 0.01, 0.01, 0.01, 0.95],
    ]}
    guess = decode_prediction(data)
    assert guess.text == 'A7B3'
    assert guess.score == pytest.approx(0.95)


def test_low_character_score_is_not_hidden_by_blank_scores():
    engine = Mock()
    engine.classification.return_value = prediction(score=0.6)
    reader = CaptchaReader(min_score=0.9, engine_factory=lambda: engine)
    assert reader.recognize(b'image') is None


@pytest.mark.parametrize('invalid', ['中', ' ', '!'])
def test_non_alphanumeric_output_rejected(invalid):
    data = prediction()
    data['charset'][1] = invalid
    assert decode_prediction(data) is None


def test_model_is_reused_and_ocr_is_local():
    engine = Mock()
    engine.classification.return_value = prediction()
    factory = Mock(return_value=engine)
    reader = CaptchaReader(engine_factory=factory)
    assert reader.recognize(b'first').text == 'A7B3'
    assert reader.recognize(b'second').text == 'A7B3'
    factory.assert_called_once()
    engine.classification.assert_called_with(b'second', probability=True)


def test_missing_optional_model_falls_back_without_reloading():
    factory = Mock(side_effect=ImportError('not installed'))
    reader = CaptchaReader(engine_factory=factory)
    assert reader.recognize(b'image') is None
    assert reader.recognize(b'image') is None
    factory.assert_called_once()


def test_malformed_prediction_falls_back():
    engine = Mock()
    engine.classification.return_value = {'wrong': 'format'}
    assert CaptchaReader(engine_factory=lambda: engine).recognize(b'image') is None


def test_ocr_success_skips_manual_input(monkeypatch):
    manual = Mock(side_effect=AssertionError('manual input should not be called'))
    monkeypatch.setattr('thsr_ticket.controller.first_page_flow._input_security_code', manual)
    reader = Mock()
    reader.recognize.return_value = CaptchaGuess('A7B3', 0.98)
    page = FirstPageFlow(Mock(), captcha_reader=reader)
    assert page.read_security_code(b'image') == 'A7B3'
    assert page.used_ocr


def test_ocr_failure_uses_manual_input(monkeypatch):
    monkeypatch.setattr('thsr_ticket.controller.first_page_flow._input_security_code', lambda image: 'Z9X2')
    reader = Mock()
    reader.recognize.return_value = None
    page = FirstPageFlow(Mock(), captcha_reader=reader)
    assert page.read_security_code(b'image') == 'Z9X2'
    assert not page.used_ocr


def test_check_connection_does_not_submit_any_form():
    client = HTTPRequest()
    client.sess.request = Mock(side_effect=[response(html('booking')), response(b'image', 'image/png')])
    reader = Mock()
    reader.recognize.return_value = CaptchaGuess('A7B3', 0.98)
    check_connection(client, reader)
    assert [call.args[0] for call in client.sess.request.call_args_list] == ['GET', 'GET']


def test_server_rejection_disables_ocr(monkeypatch, tmp_path):
    client = HTTPRequest()
    client.sess.request = Mock(side_effect=[response(html('booking')), response(b'image', 'image/png'),
                                            response(b'<span class="feedbackPanelERROR">invalid captcha</span>')])
    reader = Mock()
    reader.recognize.return_value = CaptchaGuess('A7B3', 0.98)
    monkeypatch.setattr('thsr_ticket.controller.booking_flow.ParamDB', lambda: ParamDB(str(tmp_path / 'history.json')))
    inputs = iter([''] * 11 + ['0'])
    monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
    flow = BookingFlow(client=client, captcha_reader=reader)
    flow.run()
    assert flow.captcha_reader is None
    assert client.sess.request.call_count == 3


def test_http_preserves_user_date_and_session_hidden_fields():
    client = HTTPRequest()
    page = html('booking').replace(
        b'</form>', b'<input type="hidden" name="toTimeInputField" value="2000/01/01"></form>'
    )
    client.sess.request = Mock(side_effect=[response(page), response(html('trains'))])
    client.request_booking_page()
    client.submit_booking_form({'toTimeInputField': '2099/01/01', 'BookingS1Form:hf:0': ''})
    data = client.sess.request.call_args.kwargs['data']
    assert data['toTimeInputField'] == '2099/01/01'
    assert data['BookingS1Form:hf:0'] == 'session-token'


def test_query_only_stops_before_train_selection(monkeypatch, tmp_path, capsys):
    client = HTTPRequest()
    client.sess.request = Mock(side_effect=[response(html('booking')), response(b'image', 'image/png'),
                                            response(html('trains'))])
    reader = Mock()
    reader.recognize.return_value = CaptchaGuess('A7B3', 0.98)
    monkeypatch.setattr('thsr_ticket.controller.booking_flow.ParamDB', lambda: ParamDB(str(tmp_path / 'history.json')))
    inputs = iter([''] * 11)
    monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
    flow = BookingFlow(client=client, captcha_reader=reader)
    result = flow.run(query_only=True)
    assert result.content == html('trains')
    assert [call.args[0] for call in client.sess.request.call_args_list] == ['GET', 'GET', 'POST']
    assert '0615' in capsys.readouterr().out
    assert flow.db.get_history() == []

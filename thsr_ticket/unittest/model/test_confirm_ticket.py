import pytest
from jsonschema import ValidationError

from thsr_ticket.model.web.confirm_ticket import ConfirmTicket


@pytest.fixture
def ticket():
    return ConfirmTicket()


@pytest.mark.parametrize("val", ["tooshort", "toooooooooolong"])
def test_set_id(val, ticket):
    with pytest.raises(ValueError):
        ticket.personal_id = val


@pytest.mark.parametrize("val,err_msg", [
    ("0812345667", "Wrong prefix"),
    ("0911244", "Wrong length")
])
def test_phone(val, err_msg, ticket):
    with pytest.raises(ValueError) as exc_info:
        ticket.phone = val
    assert err_msg in str(exc_info.value)
    ticket.phone = "0945789123"
    assert ticket.phone == "0945789123"


def test_get_params(ticket):
    expected = {
        "BookingS3FormSP:hf:0": "",
        "diffOver": 1,
        "idInputRadio": 0,
        "dummyId": "A186902624",
        "dummyPhone": "0945789123",
        "TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup": 'radio1',
        "email": "",
        "agree": "on",
        "isGoBackM": "",
        "backHome": "",
        "TgoError": "1"
    }

    with pytest.raises(ValidationError):
        ticket.get_params()

    ticket.personal_id = "A186902624"
    ticket.phone = '0945789123'
    ticket.member_radio = 'radio1'
    assert ticket.personal_id == "A186902624"
    assert ticket.get_params() == expected

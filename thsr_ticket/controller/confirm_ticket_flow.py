import json
from typing import Tuple

from bs4 import BeautifulSoup
from requests.models import Response
from thsr_ticket.configs.web.param_schema import ConfirmTicketModel

from thsr_ticket.model.db import Record
from thsr_ticket.remote.http_request import HTTPRequest


class ConfirmTicketFlow:
    def __init__(self, client: HTTPRequest, train_resp: Response, record: Record = None):
        self.client = client
        self.train_resp = train_resp
        self.record = record

    def run(self) -> Tuple[Response, ConfirmTicketModel]:
        page = BeautifulSoup(self.train_resp.content, features='html.parser')
        ticket_model = ConfirmTicketModel(
            personal_id=self.set_personal_id(),
            phone_num=self.set_phone_num(),
            member_radio=_parse_member_radio(page),
        )

        json_params = ticket_model.json(by_alias=True)
        dict_params = json.loads(json_params)
        resp = self.client.submit_ticket(dict_params)
        return resp, ticket_model

    def set_personal_id(self) -> str:
        if self.record and (personal_id := self.record.personal_id):
            return personal_id

        while True:
            try:
                return ConfirmTicketModel.check_personal_id(input('輸入身分證字號：\n'))
            except ValueError as exc:
                print(str(exc))

    def set_phone_num(self) -> str:
        if self.record and (phone_num := self.record.phone):
            return phone_num

        while True:
            try:
                return ConfirmTicketModel.check_phone(input('輸入手機號碼（可留空）：\n'))
            except ValueError as exc:
                print(str(exc))


def _parse_member_radio(page: BeautifulSoup) -> str:
    candidates = page.find_all(
        'input',
        attrs={
            'name': 'TicketMemberSystemInputPanel:TakerMemberSystemDataView:memberSystemRadioGroup'
        },
    )
    tag = next((cand for cand in candidates if 'checked' in cand.attrs), None)
    if tag is None:
        raise ValueError('找不到會員選項，網站頁面可能已變更。')
    return tag.attrs['value']

import json
from typing import List, Tuple

from requests.models import Response

from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.view_model.avail_trains import AvailTrains
from thsr_ticket.configs.web.param_schema import Train, ConfirmTrainModel
from thsr_ticket.view.input_utils import read_int


class ConfirmTrainFlow:
    def __init__(self, client: HTTPRequest, book_resp: Response):
        self.client = client
        self.book_resp = book_resp

    def run(self) -> Tuple[Response, ConfirmTrainModel]:
        trains = AvailTrains().parse(self.book_resp.content)
        if not trains:
            raise ValueError('目前沒有可選車次，請重新查詢。')

        selection = self.select_available_trains(trains)
        if selection is None:
            return self.book_resp, None
        confirm_model = ConfirmTrainModel(selected_train=selection)
        json_params = confirm_model.json(by_alias=True)
        dict_params = json.loads(json_params)
        resp = self.client.submit_train(dict_params)
        return resp, confirm_model

    def select_available_trains(self, trains: List[Train], default_value: int = 1) -> str:
        for idx, train in enumerate(trains, 1):
            print(
                f'{idx}. {train.id:>4} {train.depart:>3}~{train.arrive} {train.travel_time:>3} '
                f'{train.discount_str}'
            )
        selection = read_int(f'輸入選擇（0 重新查詢，預設：{default_value}）：', 0, len(trains), default_value)
        if selection == 0:
            return None
        return trains[selection-1].form_value

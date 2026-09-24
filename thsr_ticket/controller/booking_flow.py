from requests.models import Response

from thsr_ticket.controller.confirm_train_flow import ConfirmTrainFlow
from thsr_ticket.controller.confirm_ticket_flow import ConfirmTicketFlow
from thsr_ticket.controller.first_page_flow import FirstPageFlow
from thsr_ticket.view_model.error_feedback import ErrorFeedback
from thsr_ticket.view_model.booking_result import BookingResult
from thsr_ticket.view.web.show_error_msg import ShowErrorMsg
from thsr_ticket.view.web.show_booking_result import ShowBookingResult
from thsr_ticket.view.common import history_info
from thsr_ticket.model.db import ParamDB, Record
from thsr_ticket.remote.http_request import HTTPRequest
from thsr_ticket.view.input_utils import read_int


class BookingFlow:
    def __init__(self) -> None:
        self.client = HTTPRequest()
        self.db = ParamDB()
        self.record = Record()

        self.error_feedback = ErrorFeedback()
        self.show_error_msg = ShowErrorMsg()

    def run(self) -> Response:
        self.show_history()

        while True:
            # Start a fresh query after a captcha error or a user-requested search.
            book_resp, book_model = FirstPageFlow(client=self.client, record=self.record).run()
            if self.show_error(book_resp.content):
                if read_int('重新查詢並取得新驗證碼？1 是 / 0 結束（預設 0）：', 0, 1, 0):
                    continue
                return book_resp

            try:
                train_resp, train_model = ConfirmTrainFlow(self.client, book_resp).run()
            except ValueError as exc:
                print(str(exc))
                if read_int('重新查詢？1 是 / 0 結束（預設 0）：', 0, 1, 0):
                    continue
                return book_resp
            if train_model is None:
                self.record = Record()
                continue
            if self.show_error(train_resp.content):
                if read_int('重新查詢？1 是 / 0 結束（預設 0）：', 0, 1, 0):
                    continue
                return train_resp
            break

        # Final page. Ticket confirmation
        ticket_resp, ticket_model = ConfirmTicketFlow(self.client, train_resp, self.record).run()
        if self.show_error(ticket_resp.content):
            return ticket_resp

        # Result page.
        try:
            result_model = BookingResult().parse(ticket_resp.content)
        except ValueError:
            print('訂票已送出，但無法解析結果。請至高鐵官網確認訂位狀態，避免重複訂票。')
            return ticket_resp
        book = ShowBookingResult()
        book.show(result_model)
        print("\n請使用官方提供的管道完成後續付款以及取票!!")

        if read_int('在本機保存身分證、手機與行程供下次使用？1 是 / 0 否（預設 0）：', 0, 1, 0):
            try:
                self.db.save(book_model, ticket_model)
            except OSError:
                print('訂票已完成，但無法保存本機紀錄。')
        return ticket_resp

    def show_history(self) -> None:
        hist = self.db.get_history()
        if not hist:
            return
        h_idx = history_info(hist)
        if h_idx is not None:
            self.record = hist[h_idx]

    def show_error(self, html: bytes) -> bool:
        errors = self.error_feedback.parse(html)
        if len(errors) == 0:
            return False

        self.show_error_msg.show(errors)
        return True

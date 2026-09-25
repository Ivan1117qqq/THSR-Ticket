import argparse
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from requests import RequestException
from bs4 import BeautifulSoup
from thsr_ticket.captcha import CaptchaReader
from thsr_ticket.controller.booking_flow import BookingFlow
from thsr_ticket.controller.first_page_flow import (
    _parse_seat_prefer_value, _parse_types_of_trip_value, _parse_search_by,
)
from thsr_ticket.remote.http_request import HTTPRequest


def main() -> int:
    parser = argparse.ArgumentParser(description='高鐵命令列訂票小幫手')
    parser.add_argument('--browser', choices=['chrome', 'msedge'], help='使用獨立瀏覽器工作階段連線')
    parser.add_argument('--headless', action='store_true', help='瀏覽器在背景執行')
    parser.add_argument('--auto-captcha', action='store_true', help='啟用本機 OCR，不確定時改為手動輸入')
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument('--check-connection', action='store_true', help='只測試首頁、表單及驗證碼，不送出查詢或訂票')
    checks.add_argument('--query-only', action='store_true', help='查詢並列出車次後停止，不選車或訂票')
    args = parser.parse_args()
    if args.headless and not args.browser:
        parser.error('--headless 必須搭配 --browser。')
    client = None
    try:
        if args.browser:
            from thsr_ticket.remote.browser_request import BrowserRequest
            client = BrowserRequest(channel=args.browser, headless=args.headless)
        else:
            client = HTTPRequest(max_retries=0, timeout=15)
        reader = CaptchaReader() if args.auto_captcha else None
        if args.check_connection:
            check_connection(client, reader)
        else:
            BookingFlow(client=client, captcha_reader=reader).run(query_only=args.query_only)
    except (EOFError, KeyboardInterrupt):
        print('\n已結束。')
        return 130
    except RequestException:
        if args.query_only or args.check_connection:
            print('查詢連線失敗或逾時；本次未建立訂位。')
        else:
            print('連線失敗或逾時。若剛送出訂票，請先至高鐵官網確認訂位狀態再操作。')
        return 1
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'無法繼續：{exc}')
        return 1
    finally:
        if client is not None:
            client.close()
    return 0


def check_connection(client: HTTPRequest, reader: CaptchaReader = None) -> None:
    response = client.request_booking_page()
    if 'BookingS1Form' not in client.form_actions:
        raise ValueError('首頁未包含訂票表單。')
    page = BeautifulSoup(response.content, 'html.parser')
    _parse_seat_prefer_value(page)
    _parse_types_of_trip_value(page)
    _parse_search_by(page)
    image = client.request_security_code_img(response.content)
    if not image.headers.get('Content-Type', '').startswith('image/'):
        raise ValueError('驗證碼回應不是圖片。')
    print('首頁、表單與驗證碼圖片可讀取；未送出查詢或訂票。')
    if reader is not None:
        guess = reader.recognize(image.content)
        if guess:
            print(f'OCR 候選：{guess.text}（未送出驗證，不能視為辨識正確）')
        else:
            print('OCR 無可靠結果，訂票時將改為手動輸入。')


if __name__ == "__main__":
    sys.exit(main())

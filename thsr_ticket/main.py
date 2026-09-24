import argparse
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from requests import RequestException
from thsr_ticket.controller.booking_flow import BookingFlow


def main() -> int:
    parser = argparse.ArgumentParser(description='高鐵命令列訂票小幫手（驗證碼需手動輸入）')
    parser.parse_args()
    try:
        flow = BookingFlow()
        flow.run()
    except (EOFError, KeyboardInterrupt):
        print('\n已結束。')
        return 130
    except RequestException:
        print('連線失敗或逾時。若剛送出訂票，請先至高鐵官網確認訂位狀態再操作。')
        return 1
    except (ValueError, OSError) as exc:
        print(f'無法繼續：{exc}')
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

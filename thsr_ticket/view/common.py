from typing import Iterable

from thsr_ticket.model.db import Record
from thsr_ticket.model.web.booking_form.station_mapping import StationMapping
from thsr_ticket.view.input_utils import mask_private, read_int


def history_info(hists: Iterable[Record], select: bool = True) -> int:
    hists = list(hists)
    for idx, r in enumerate(hists, 1):
        print("第{}筆紀錄".format(idx))
        print("  身分證字號: " + mask_private(r.personal_id or ''))
        print("  手機號碼: " + mask_private(r.phone or ''))
        print("  起程站: " + StationMapping(r.start_station).name)
        print("  到達站: " + StationMapping(r.dest_station).name)
        t_str = r.outbound_time
        print("  出發時間: {}:{} (A: 早上, P: 下午, N: 中午)".format(t_str[:-3], t_str[-3:]))
        print("  大人票數: " + r.adult_num[:-1])

    if select:
        sel = read_int("請選擇紀錄或是 Enter 跳過: ", 0, len(hists), 0)
        return sel - 1 if sel else None
    return None

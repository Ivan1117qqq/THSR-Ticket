"""Conservative local journey dates, payment reminders and bounded calendar views."""
import calendar
import hashlib
import re
from datetime import date, datetime, time

from thsr_ticket.automation import TAIPEI
from thsr_ticket.scan_report import check_cancel


def full_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', value):
        return None
    try:
        return date(*map(int, re.split('[-/]', value)))
    except ValueError:
        return None


def deadline_time(value):
    """No guessed year, end-of-day or official payment status."""
    if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?', value.strip()):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace('/', '-'))
        return parsed.replace(tzinfo=TAIPEI) if parsed.tzinfo is None else parsed.astimezone(TAIPEI)
    except ValueError:
        return None


def journey_date(ticket):
    raw = str(ticket.get('date', ''))
    actual, requested = full_date(raw), full_date(ticket.get('requested_outbound_date', ''))
    if actual:
        return actual if requested is None or actual == requested else None
    if requested and re.fullmatch(r'\d{1,2}[/\-]\d{1,2}', raw):
        month, day = map(int, re.split(r'[/\-]', raw))
        return requested if (month, day) == (requested.month, requested.day) else None
    return requested if requested and not raw.strip('— ') else None


class PlanningIndex:
    def __init__(self, records, cancel=None):
        self.source = records
        self.rows, self.by_day = [], {}
        for item in records:
            check_cancel(cancel)
            if item.get('resolution') in ('cancelled', 'not_booked') or item.get('official_status') == 'cancelled':
                continue
            ticket = item.get('ticket', {})
            day = journey_date(ticket)
            code = str(item.get('code', ''))
            official = item.get('official_status', '')
            booked = bool(code) and (item.get('status') in ('booked', 'history')
                                     or (item.get('status') == 'resolved' and item.get('resolution') == 'booked'))
            pending = bool(item.get('current') and not booked)
            payable = booked and official not in ('paid', 'collected') and (
                item.get('current') or official == 'unpaid')
            key = hashlib.sha256('\0'.join((code, str(day), str(ticket.get('train_id', '')),
                                           str(ticket.get('start_station', '')),
                                           str(ticket.get('dest_station', '')))).encode()).hexdigest()
            row = {'id': key, 'date': day.isoformat() if day else '', 'time': str(ticket.get('depart_time', '')),
                   'route': (str(ticket.get('start_station') or '待核對') + ' → '
                             + str(ticket.get('dest_station') or '待核對')),
                   'train': str(ticket.get('train_id', '')), 'pending': pending, 'payable': bool(payable),
                   'booked': booked,
                   'status': ('待核對' if pending else {'paid': '已付款', 'collected': '已取票',
                                                     'unpaid': '待繳費'}.get(official, '付款待核對' if payable else '歷史紀錄')),
                   'raw_deadline': str(ticket.get('payment_deadline', ''))[:120]}
            self.rows.append(row)
            if day and (booked or pending):
                self.by_day.setdefault(day.isoformat(), []).append(row)

    def calendar(self, year, month, selected):
        first = date(year, month, 1)
        offset, count = calendar.monthrange(year, month)
        cells = []
        for number in range(42):
            day = number - offset + 1
            iso = date(year, month, day).isoformat() if 1 <= day <= count else ''
            cells.append({'day': day if iso else 0, 'date': iso, 'count': len(self.by_day.get(iso, []))})
        entries = sorted(self.by_day.get(selected, []), key=lambda item: item['time'])
        return {'title': f'{first.year} 年 {first.month} 月', 'cells': cells,
                'items': entries[:8], 'total': len(entries)}

    def agenda(self, now, overrides):
        pending, payable, upcoming = 0, 0, 0
        items, reminders = [], []
        for row in self.rows:
            value = dict(row)
            day = full_date(row['date'])
            has_time = bool(re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', row['time']))
            departure = datetime.combine(day, time.fromisoformat(row['time']), TAIPEI) if day and has_time else None
            future = bool(day and (departure >= now if departure else day >= now.date()))
            pending += row['pending']
            upcoming += future and row['booked']
            payable += row['payable'] and (future or day is None)
            local = row['id'] in overrides
            deadline = deadline_time(overrides.get(row['id'], '') if local else row['raw_deadline'])
            if deadline and day and (deadline > departure if departure else deadline.date() > day):
                deadline = None
            value.update(deadline=deadline.isoformat() if deadline else '', local_deadline=local,
                         remaining='期限待確認', expired=False)
            if deadline:
                seconds = int((deadline - now).total_seconds())
                value['expired'] = seconds <= 0
                minutes = max(0, (seconds + 59) // 60)
                value['remaining'] = '已過本機期限，請核對' if seconds <= 0 else (
                    f'剩餘 {minutes // 1440} 天 {(minutes % 1440) // 60} 小時' if minutes >= 1440 else
                    f'剩餘 {minutes // 60} 小時 {minutes % 60} 分')
                if row['payable'] and future and seconds > 0:
                    reminders.append(value)
            if row['pending'] or (row['payable'] and (future or day is None)):
                items.append(value)
        items.sort(key=lambda item: (not item['pending'], item['deadline'] or '9999', item['date']))
        return {'pending': pending, 'payment': payable, 'upcoming': upcoming, 'items': items[:6],
                'total': len(items), 'reminders': reminders}

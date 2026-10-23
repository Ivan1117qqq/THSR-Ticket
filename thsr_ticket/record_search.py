"""Immutable record snapshot, normalized search documents and bounded filter cache."""
import json
from collections import OrderedDict

from thsr_ticket.scan_report import check_cancel


class RecordSearchIndex:
    PAGE_SIZE = 25
    CACHE_SIZE = 8
    STATUSES = ('', 'booked', 'submission_pending', 'resolved', 'history')

    def __init__(self, records, cancel=None):
        self.source = records
        self.documents = []
        self.current_count = 0
        self.filter_passes = 0
        self._cache = OrderedDict()
        for item in records:
            check_cancel(cancel)
            ticket = item.get('ticket', {})
            current = bool(item.get('current'))
            text = (str(item.get('code', '')) + ' ' + json.dumps(ticket, ensure_ascii=False)).casefold()
            self.documents.append((current, item.get('status', ''), str(ticket.get('date', '')), text))
            self.current_count += current

    def page(self, history, search, day, status, page):
        if not 0 <= status < len(self.STATUSES):
            return {'items': [], 'total': 0, 'pages': 1}
        key = (bool(history), search.strip().casefold(), day.strip(), status)
        if key in self._cache:
            matching = self._cache.pop(key)
        else:
            self.filter_passes += 1
            history, search, day, status = key
            matching = tuple(index for index, (current, code, date, text) in enumerate(self.documents)
                             if (history or current) and (not status or code == self.STATUSES[status])
                             and (not day or day in date) and (not search or search in text))
        self._cache[key] = matching
        while len(self._cache) > self.CACHE_SIZE:
            self._cache.popitem(last=False)
        pages = max(1, (len(matching) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = max(0, min(page, pages - 1))
        selected = matching[page * self.PAGE_SIZE:(page + 1) * self.PAGE_SIZE]
        return {'items': [self.source[index] for index in selected], 'total': len(matching), 'pages': pages}

"""Search one immutable record snapshot; no disk or website required."""
import threading

import pytest

from thsr_ticket.record_search import RecordSearchIndex
from thsr_ticket.scan_report import ScanCancelled


def records(count=100):
    return [{'code': f'{number:08d}', 'current': number == 0,
             'status': 'booked' if number == 0 else 'history',
             'ticket': {'date': '2099-01-15', 'start_station': '台北', 'dest_station': '台中',
                        'train_id': 'AB0117'}} for number in range(count)]


def test_normalized_search_combines_filters_and_clamps_page():
    index = RecordSearchIndex(records())
    assert index.current_count == 1
    data = index.page(True, '  ab0117  ', '2099-01', 4, 999)
    assert data['total'] == 99 and data['pages'] == 4
    assert len(data['items']) == 24 and data['items'][-1]['code'] == '00000099'
    assert index.page(False, '台中', '', 0, -1)['items'][0]['code'] == '00000000'
    assert index.page(True, 'missing', '', 0, 0) == {'items': [], 'total': 0, 'pages': 1}
    assert index.page(True, '', '', -1, 0)['total'] == 0
    assert index.page(True, '', '', 5, 0)['total'] == 0


def test_paging_and_equivalent_search_reuse_filter_without_serializing_again(monkeypatch):
    index = RecordSearchIndex(records())
    index.page(True, 'AB0117', '', 0, 0)

    def unexpected_serialization(*args, **kwargs):
        raise AssertionError('Search must use the normalized document')

    monkeypatch.setattr('thsr_ticket.record_search.json.dumps', unexpected_serialization)
    result = index.page(True, '  ab0117 ', '', 0, 1)
    assert result['items'][0]['code'] == '00000025' and index.filter_passes == 1


def test_filter_cache_is_bounded_lru():
    index = RecordSearchIndex(records())
    for number in range(index.CACHE_SIZE):
        index.page(True, str(number), '', 0, 0)
    index.page(True, '0', '', 0, 0)  # Keep the oldest key alive.
    index.page(True, 'extra', '', 0, 0)
    assert len(index._cache) == index.CACHE_SIZE
    before = index.filter_passes
    index.page(True, '0', '', 0, 0)
    assert index.filter_passes == before
    index.page(True, '1', '', 0, 0)
    assert index.filter_passes == before + 1


def test_new_snapshot_does_not_reuse_previous_matches():
    before = RecordSearchIndex(records(1))
    assert before.page(True, '台中', '', 0, 0)['total'] == 1
    replacement = records(1)
    replacement[0]['ticket']['dest_station'] = '左營'
    after = RecordSearchIndex(replacement)
    assert after.page(True, '台中', '', 0, 0)['total'] == 0
    assert after.page(True, '左營', '', 0, 0)['total'] == 1


def test_index_preparation_honors_cancellation():
    cancel = threading.Event()

    def entries():
        yield records(1)[0]
        cancel.set()
        yield records(1)[0]

    with pytest.raises(ScanCancelled):
        RecordSearchIndex(entries(), cancel)

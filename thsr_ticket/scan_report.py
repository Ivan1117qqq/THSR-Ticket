"""Count scan outcomes with fixed labels; no raw filenames or exception text."""
from collections import Counter

LABELS = {
    'unsupported': '不支援的目錄或額外檔案',
    'linked': '連結目錄或檔案',
    'unfinished': '執行尚未結束',
    'malformed': '內容損壞或格式不完整',
    'version': '紀錄版本不支援',
    'permission': '權限不足或檔案占用',
    'missing': '掃描時檔案已移動或刪除',
    'io': '檔案讀取失敗',
}
FAILED = {'permission', 'missing', 'io'}


class ScanCancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ScanCancelled()


def children(path):
    """Missing roots are empty; inaccessible roots must not look like empty results."""
    try:
        yield from path.iterdir()
    except FileNotFoundError:
        if path.exists():
            raise


class ScanReport:
    def __init__(self):
        self.accepted = 0
        self.reasons = Counter()

    def skip(self, reason):
        self.reasons[reason] += 1

    def failure(self, error):
        if isinstance(error, PermissionError) or getattr(error, 'winerror', None) in (5, 32, 33):
            self.skip('permission')
        elif isinstance(error, FileNotFoundError):
            self.skip('missing')
        else:
            self.skip('io')

    def snapshot(self):
        failed = sum(count for reason, count in self.reasons.items() if reason in FAILED)
        skipped = sum(self.reasons.values()) - failed
        return {'accepted': self.accepted, 'skipped': skipped, 'failed': failed,
                'checked': self.accepted + skipped + failed,
                'reasons': [{'code': reason, 'label': LABELS[reason], 'count': count}
                            for reason, count in sorted(self.reasons.items())]}

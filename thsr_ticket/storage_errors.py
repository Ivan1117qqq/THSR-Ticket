"""Stable storage error codes and user guidance; never expose raw exception text."""


class StorageError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


ERRORS = {
    'permission_denied': ('無法存取紀錄或備份', '請關閉可能占用檔案的程式，確認資料夾寫入權限後重新掃描。'),
    'operation_busy': ('另一個訂位或紀錄操作仍在執行', '請停止該任務並等候結束，再重新掃描。'),
    'records_changed': ('所選紀錄已變更或不存在', '請重新掃描，再勾選要整理的紀錄。'),
    'booking_guard': ('目前仍有訂位狀態', '請先到「我的訂位」核對官網結果並封存本機狀態。'),
    'restore_conflict': ('原位置已有同名紀錄', '請保留兩側資料；確認重複紀錄前，不要覆寫或刪除。'),
    'unsafe_path': ('資料位置含連結或不支援的路徑', '請使用一般本機資料夾，確認位置後重新載入設定。'),
    'backup_invalid': ('備份結構不完整或格式不支援', '請保留備份，確認使用相容版本的程式，不要手動覆寫。'),
    'recovery_required': ('找到尚未完成的紀錄操作', '請到「中斷復原」檢查批次，確認後回復操作前位置。'),
    'recovery_conflict': ('資料已變更，無法安全回復', '請保留原位置、備份及操作清單，先人工核對；程式不會覆寫。'),
    'journal_invalid': ('操作清單損壞或版本不支援', '請保留操作清單與兩側紀錄，使用相容版本或人工協助處理。'),
    'rollback_failed': ('操作中斷，部分紀錄尚待復原', '請保留兩側資料，排除權限或占用問題後，到「中斷復原」重試。'),
    'disk_full': ('磁碟空間不足', '請先釋放其他檔案的空間，保留訂位資料與備份，再重新掃描。'),
    'io_error': ('檔案讀寫失敗', '請確認磁碟與資料夾可用；重新掃描並檢查是否出現待復原批次。'),
    'worker_start_failed': ('無法啟動背景工作', '請關閉並重新開啟程式，再執行紀錄操作。'),
    'unexpected_error': ('紀錄操作遇到未預期錯誤', '請保留資料與備份，重開程式並檢查「中斷復原」。'),
}


def error_info(error):
    from thsr_ticket.record_lock import RecordBusy
    if isinstance(error, StorageError):
        code = error.code if error.code in ERRORS else 'unexpected_error'
    elif isinstance(error, RecordBusy):
        code = 'operation_busy'
    elif isinstance(error, PermissionError) or getattr(error, 'winerror', None) in (5, 32, 33):
        code = 'permission_denied'
    elif isinstance(error, FileNotFoundError):
        code = 'records_changed'
    elif getattr(error, 'errno', None) == 28 or getattr(error, 'winerror', None) == 112:
        code = 'disk_full'
    elif isinstance(error, OSError):
        code = 'io_error'
    else:
        code = 'unexpected_error'
    title, guidance = ERRORS[code]
    return {'code': code, 'title': title, 'guidance': guidance}

"""Stable storage error codes and user guidance; never expose raw exception text."""


class StorageError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


ERRORS = {
    'ocr_report_destination': ('請另選評估摘要檔案', '請選擇訂位資料目錄以外的 .ocr-report.json 新檔案；不能覆寫設定或紀錄。'),
    'official_unrecognized': ('無法核對官網頁面', '網站格式不符或需要人工檢測；原訂位與防重送紀錄保留，請至官網核對。'),
    'official_query_rejected': ('官網未回傳訂位明細', '請確認驗證碼、取票識別碼與代碼。查無資料不代表訂位未成立。'),
    'official_mismatch': ('訂位資料未通過核對', '代碼、日期、起訖站及車次必須一致；請保留紀錄並核對官網。'),
    'official_cancel_unavailable': ('這筆訂位無法由程式取消', '目前只支援已核對的未付款單程訂位；已付款、已取票或不明頁面請在官網處理。'),
    'official_unconfirmed': ('取消結果待確認', '取消已嘗試送出，請重新查詢官網；程式不會自動重送或移除防重送狀態。'),
    'official_captcha': ('請輸入四碼驗證碼', '依畫面人工輸入英數字；需要時可換圖，程式不會連續自動嘗試。'),
    'cleanup_partial': ('清理部分完成', '請重新預覽；已保留操作摘要，尚未刪除的資料仍在原位置。'),
    'backup_config_missing': ('尚無可備份的設定', '請先儲存個人行程設定，再預覽完整備份。'),
    'backup_source_changed': ('備份來源已變更', '請重新預覽來源或備份檔，再確認操作。'),
    'backup_limit': ('資料超出本版備份限制', '每份最多 20000 個檔案、總計 2 GiB，單檔最多 256 MiB；請保留原始資料。'),
    'backup_extension': ('請使用完整備份副檔名', '請另選新的 .thsr-backup.zip 檔名。'),
    'backup_destination_exists': ('目的位置已存在', '請改選新的檔名或還原資料夾；不會合併或覆寫既有資料。'),
    'backup_restore_pending': ('還原尚未完成', '請保留該資料夾，重新還原到新的位置，不要移除待核對狀態或未完成標記。'),
    'backup_config_locked': ('還原完成，設定暫時無法載入', '資料已保留；受保護欄位需要原 Windows 帳號及電腦環境。格式損壞或版本不支援時請保留原檔。'),
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

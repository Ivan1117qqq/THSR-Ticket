# 高鐵訂票小幫手

以 Python 命令列操作高鐵單程訂票，提供互動填寫與預先設定的定時自動訂位兩種模式。
支援本機驗證碼 OCR；自動模式可在指定時間開始查票，依設定間隔重查，找到符合條件的車次後送出訂位，取得訂位代碼即停止，不付款。

目前已完成一次實站 OCR 車次查詢並解析 10 筆車次；**選車與最終訂位僅通過離線模擬，尚未驗證實站訂位成功**。
查詢速度取決於網頁載入、辨識及網站回應，不保證搶票成功。

## 安裝

已驗證環境為 Windows、CPython 3.13.5 與已安裝的 Chrome。以下從本專案分支安裝，包含瀏覽器及 OCR 套件：

```powershell
git clone https://github.com/Ivan1117qqq/THSR-Ticket.git
cd THSR-Ticket
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-automation-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m thsr_ticket.main --help
```

以下指令統一使用新建環境的 `.venv\Scripts\python.exe`。
**目前開發工作區已有的環境位於 `.venv\windows\Scripts\python.exe`**；若使用該環境，請替換路徑，不需重建。
只使用 HTTP 與手動驗證碼時，可改裝 `requirements-lock.txt`；先前實站測試 HTTP 模式曾逾時。

## 定時自動訂位

先建立個人設定檔：

```powershell
Copy-Item booking.example.json booking.local.json
notepad booking.local.json
```

將範例的 2099 年日期與身分證提示文字改成實際資料，並設定：

不清楚欄位時，先看 [逐欄填寫指南與車站代碼](docs/automation.md#設定欄位)。
`start_at` 是開始查票的時間，`outbound_date` 才是搭車日期；已建立 `booking.local.json` 就直接編輯，避免重新複製範本覆蓋資料。

- `start_at`：開始查詢時間，未指定時區視為台灣時間；已過時間則立即開始。
- `interval_seconds`：每輪查詢完成後的等待秒數，例如 `1` 或 `0.5`，請求不重疊。
- `max_attempts`：最多查詢次數，達上限即停止。
- 起訖站、乘車日期、可接受時段、票種張數與車廂。
- `train_ids`：可接受車次的優先順序；空陣列表示選擇回傳結果中最早符合時段的車次。
- `personal_id`、`phone_num`：乘客證號與手機。

先離線驗證設定，再啟動：

```powershell
# 只驗證設定，不開瀏覽器或連線
.\.venv\Scripts\python.exe -m thsr_ticket.main --config booking.local.json --validate-config

# 定時查票並自動送出訂位，不付款
.\.venv\Scripts\python.exe -m thsr_ticket.main --config booking.local.json
```

自動模式預設使用 Chrome 及本機 OCR，會先載入瀏覽器與模型再等待設定時間；電腦需保持開機且不要睡眠。
`0.5` 秒是兩輪間的等待時間，不代表每半秒完成一次查詢。
若要只查票，在啟動指令加上 `--query-only`，找到符合條件的車次後會停止，不選車或訂位。

OCR 無可靠結果、驗證碼遭拒、未知網站錯誤或網路失敗時，自動模式會停止，不等待輸入。
送出最終訂位前會建立 `booking.local.state.json`；成功時保存訂位代碼，結果不明時保留待確認紀錄。
再次使用同一設定檔訂位會停止，請先至官網確認狀態，再自行處理紀錄，避免重複訂位。

完整欄位、無票重查條件與復原方式見 [自動訂位說明](docs/automation.md)。

## 互動訂票與連線檢查

不加 `--config` 時，程式會依序詢問行程、選車及乘客資料：

```powershell
# 只讀取首頁及驗證碼、測試 OCR，不送出車次查詢或訂位
.\.venv\Scripts\python.exe -m thsr_ticket.main --browser chrome --auto-captcha --check-connection

# 手動填寫行程，查詢車次後停止
.\.venv\Scripts\python.exe -m thsr_ticket.main --browser chrome --auto-captcha --query-only

# 完整互動訂票流程
.\.venv\Scripts\python.exe -m thsr_ticket.main --browser chrome --auto-captcha
```

互動模式不加 `--auto-captcha` 即手動輸入驗證碼；OCR 無可靠結果時改為手動輸入，網站拒絕 OCR 查詢後停用本次自動辨識。
可用 `--browser msedge` 選擇 Edge。`--headless` 提供背景模式，但先前實站連線失敗，尚未確認可用。
瀏覽器使用獨立暫存設定檔，結束時關閉並清理，不載入個人的 Chrome 資料。

## 功能範圍與本機資料

- 支援單程、依時間查詢；成人、孩童、愛心、敬老及大學生票，合計 1–10 張。資格與可售票種由網站判定。
- 支援標準／商務車廂；互動模式可選座位偏好，自動模式使用網站預設。
- 自動模式的指定車次是篩選查詢結果，不是網站的直接車次查詢，也不會自動翻頁搜尋整天班次。
- 尚未提供來回票、只篩早鳥、會員、護照、市話、電子郵件或付款功能；OCR 不處理其他互動式網站檢測。
- 互動模式可在成功後選擇保存部分資料至 `thsr_ticket/.db/history.json`，預設不保存；歷史列表遮蔽證號與手機，只保留末三碼。
- 自動模式的 `booking.local.json` 會保存你填寫的個資。設定檔與歷史資料皆為明文，並非加密。
  `booking.local.json`、`*.state.json` 與 `.db/` 已由 Git 忽略；自訂個資檔名也需加入忽略清單。

## 測試與驗證

```powershell
# 離線測試
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider

# 加入本機 Chrome 操作測試：攔截網站請求，不建立真實訂位
.\.venv\Scripts\python.exe -m pytest -q --browser-tests -p no:cacheprovider

# 程式風格檢查
.\.venv\Scripts\python.exe -m flake8 -j1 --config .config/flake thsr_ticket
```

2026-09-25 驗證結果：**119 項測試通過、1 項實站 HTTP 測試預設跳過，Flake8 通過**。
測試涵蓋定時等待、次秒間隔、車次篩選、無票重查、成功停止與訂位結果不明時不重送。
人工 HTML 與本機模擬不能取代實站驗證；Mypy、Pylint 與 CI 尚有待整理項目。

若需單獨測試 HTTP 首頁讀取，可執行下列指令；只讀取頁面與驗證碼，不送出訂位：

```powershell
.\.venv\Scripts\python.exe -m pytest thsr_ticket/unittest/test_http_request.py --live -q
```

詳細紀錄：[專案驗證](docs/verification.md)、[瀏覽器與 OCR](docs/browser-ocr.md)。

## 專案來源

本專案基於 [BreezeWhite/THSR-Ticket](https://github.com/BreezeWhite/THSR-Ticket)，此分支新增 Windows 驗證、瀏覽器連線、本機 OCR 與定時自動流程。

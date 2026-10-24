# 高鐵訂票小幫手

提供 Qt 桌面 App 與 Python 命令列的高鐵單程訂票工具，支援預先設定行程與定時自動訂位。
支援本機驗證碼 OCR；自動模式可在指定時間開始查票，依設定間隔重查，找到符合條件的車次後送出訂位，取得訂位代碼即停止，不付款。

既有命令列流程已有使用者回報實站訂位成功；**新版 Qt 桌面介面目前完成離線驗證，尚未進行實站訂位驗收**。
查詢速度取決於網頁載入、辨識及網站回應，不保證搶票成功。

最新原始碼支援「新增行程 → 雙鐵同時訂票」：高鐵沿用自動流程，台鐵以獨立 Chrome 預填與定時送出，必要驗證及後續選車／確認由使用者接手。依使用者需求，兩邊各訂到一筆後各自停止，不付款；不需要的票自行至官網取消。**台鐵為實驗性輔助訂票，尚待實站驗收，不宣稱全程無人操作**；設定、結果核對及保存限制見 [雙鐵使用說明](docs/dual-rail.md)。

測試台鐵可先用「預填檢查 · 不訂位」，再選「只啟動台鐵」，不用同時啟動高鐵。另提供台鐵視窗喚回、官網時段下拉、送出前有限連線重試、代碼複製與執行紀錄；啟動命令及分步驗收見 [台鐵操作](docs/dual-rail.md)。

2026-10-24 原始碼已新增雙鐵面板、常用行程範本、繳費期限提醒與首頁月曆待辦，保留既有年月日滾輪、行程核對、搜尋快取及防重送；最新本機完整驗證為 **602 項通過、1 項實站測試跳過**，包含二十項瀏覽器測試（網路全部攔截）。台鐵訂票後頁面、高鐵官網核對／取消與真實 OCR 準確率仍待指定測試資料；通知實際點擊與螢幕閱讀器仍需人工觀察。安裝包維持暫緩，操作見 [集中驗收清單](docs/acceptance.md)，交付範圍見 [確認文件](docs/optimization-audit.md)。

## 從頭學習與維護專案

2026-10-24 新增常用行程範本、首頁待辦與月曆，以及開啟 App 期間的繳費期限提醒。範本不含日期或訂票人資料，期限不明時不猜測；操作與保存範圍見 [行程管理](docs/journey-planner.md)。

- [集中驗收清單](docs/acceptance.md)：一鍵自動檢查、可操作的隔離假資料視窗，以及 U1–U11／L1–L3 的步驟與回報格式。
- [完整開發與架構指南](docs/development-guide.md)：從入口、QML、背景執行緒到訂位、防重送、測試與打包，依程式執行順序逐段說明。
- [逐檔用途與清理紀錄](docs/file-inventory.md)：列出原始碼、測試、工具與文件用途，說明哪些歷史程式已移除、哪些相容功能仍需保留。
- [開發範圍與驗收狀態](docs/roadmap.md)：分開列出已完成、外部驗收及未排程選配，避免待辦不斷擴大。
- [介面遷移設計背景](docs/app-architecture.md)：保留 Qt 改版時的取捨，現行實作以完整指南為準。
- [發行與依賴管理](docs/releasing.md)：版本來源、執行／開發／打包環境及安裝升級驗收。
- [版本紀錄](CHANGELOG.md)：各版交付功能摘要。
- [歷史診斷與桌面通知](docs/history-diagnostics.md)：過去任務的問題定位、診斷匯出及通知設定。
- [桌面介面與工具分層](docs/desktop-ui.md)：設定分頁、測試通知、錯誤欄位聚焦與程式責任。
- [完整備份與還原](docs/backup.md)：目前設定與關聯紀錄的封裝、新位置還原、衝突及防重送規則。
- [優化交付與驗收邊界](docs/optimization-audit.md)：固定五項收尾結果，以及先前斷線核對、取消、重試、清理、介面效能與 OCR 的實作範圍。
- [官網訂位核對與取消](docs/booking-management.md)：實驗性查詢同步與未付款單程取消流程，仍待實站驗收。
- [常用行程與繳費提醒](docs/journey-planner.md)：範本管理、月曆待辦、明確期限提醒及全域資料保存範圍。
- [雙鐵同時訂票](docs/dual-rail.md)：獨立工作與停止、台鐵預填／真人驗證、結果核對及本機封存。

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

## Travel Desk 桌面 App

不想手動編輯 JSON，可使用本機桌面視窗：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe -m thsr_ticket.desktop
```

目前工作區請使用 `.\.venv\windows\Scripts\python.exe -m thsr_ticket.desktop`。
新版採固定側欄、行程卡片、日期選擇與眼睛遮蔽切換；分為總覽、新增行程、任務進度、我的訂位及設定。
搭車日期與啟動日期改用年／月／日三欄滾輪，可上下拖曳、用滑鼠滾輪或方向鍵選擇，按「套用日期」才寫回表單。會處理閏年與各月天數；選啟動日期時保留原本的時、分、秒，取消則保留原值。
先「載入設定」選擇原本的 `booking.local.json`；會沿用原檔與防重送紀錄。新設定預設存於使用者 App 資料目錄。
「只查票」不訂位；「自動訂位 · 不付款」會依設定時間查詢並送出訂位，啟動前自動保存與驗證。
停止與關閉會等待目前操作及瀏覽器清理。既有訂位可在「我的訂位」移至歷史；待確認結果提供官網核對流程。
0.3.3 在同一使用者資料目錄只允許一個 Qt App；再次開啟會要求原視窗顯示並取得焦點，不另啟動任務。若原程序無回應，會提示稍後再試。
**本機封存不會取消官網訂位。**

詳細操作、資料路徑與 Windows EXE 打包見 [Travel Desk 說明](docs/desktop.md)。
最新介面的紀錄整理入口為「設定 → 資料管理 → 開啟資料管理」（0.4.0 舊入口為「設定 → 整理歷史紀錄」）：支援背景掃描、取消、日期篩選與逐筆勾選，確認後移至可還原備份；可選擇備份批次還原；不取消官網訂位、不釋放磁碟空間。整理功能已整合至 0.4.0，新的分頁入口仍為原始碼更新。
整理／還原若意外中斷，重開程式會提示「中斷復原」，核對後可回復操作前位置；錯誤畫面會提供原因與處理指引，詳見 [紀錄管理](docs/record-storage.md)。
「我的訂位」以背景載入並分頁顯示；資料管理掃描會保留可讀結果，列出略過與失敗原因。勾選採逐列更新，整理前僅重驗所選紀錄。
搜尋在停止輸入 250 毫秒後套用，按 Enter 或清空則立即更新；背景建立索引並快取篩選結果，換頁不用重新掃描整份清單。
最新原始碼另提供「設定 → 進階與關於 → 歷史任務診斷」及預設關閉的桌面通知：可選擇過去任務查看階段與處理建議，預覽後匯出過濾內容；通知點擊可回到相關頁面。這兩項尚未重新打包，現有 0.4.0 EXE 不包含，請從原始碼啟動。操作與限制見 [說明](docs/history-diagnostics.md)。
最新介面已拆分頁面與對話框，設定改為「一般偏好／資料管理／進階與關於」：通知及測試位於一般偏好，歷史診斷位於進階與關於。欄位驗證失敗會展開並聚焦錯誤位置。開發期間先使用原始碼，安裝包待主要流程穩定後再集中驗收；詳見 [介面說明](docs/desktop-ui.md)。
「設定 → 資料管理 → 完整備份與還原」可預覽並匯出目前已儲存設定及關聯紀錄，驗證後還原到新的資料夾。原有防重送紀錄保留；備份沒有狀態檔時，還原會新增待核對狀態。ZIP 未整體加密，請妥善保管；詳見 [操作與限制](docs/backup.md)。
0.3.0 提供設定記憶、時間選擇、未儲存提醒、訂位篩選、個資保護與手動更新檢查。
0.3.1 加入官網取消引導與人工確認封存、查票暫時斷線退避重試，以及網站拒絕原因分類；取消的最後確認仍在官網完成，詳見 [桌面版說明](docs/desktop.md)。
0.3.2 加入共用任務狀態卡、重新啟動後的任務摘要與對應復原入口；既有訂位狀態優先，不自動恢復或重送任務。
0.3.3 整合單一視窗、診斷預覽匯出及設定版本／備份遷移。
0.4.0 整合歷史紀錄管理、中斷復原、背景載入、掃描容錯與分頁，並統一版本及依賴管理。Windows 安裝包位於 `dist/installer/TravelDesk-Setup-0.4.0.exe`，旁附 `.sha256` 與 `dist/release.json`，目前交付未簽章版本。
這是本機建置產物，不包含在 Git 原始碼中；新 clone 不會自帶 EXE。可依桌面版說明自行打包；手動 Windows CI 可產生 artifact，但不會自動發布 GitHub Release。
舊 Tk 介面仍可用 `python -m thsr_ticket.gui` 啟動，操作見 [舊版說明](docs/gui.md)。

## 集中檢查與假資料驗收

本機開發環境可一次執行所有已準備的檢查，再開啟隔離視窗親自操作：

```powershell
.\.venv\windows\Scripts\python.exe -m scripts.verify_acceptance --native
.\.venv\windows\Scripts\python.exe -m scripts.review_desktop
```

第一個指令建立新的 `build/acceptance/<時間與識別碼>/` 報告，包含十項原本選用的瀏覽器測試；不跑 `--live`。第二個指令建立假資料及獨立偏好，不讀取日常 AppData；查票／訂位及官網動作會阻擋，只供介面與本機資料操作驗收。可用 `--case pending`、`--case logs`、`--case backup` 直接開啟其他情境，或在畫面載入同份資料夾的設定；`--scale 1.5` 可檢查縮放。

U1–U7 是需要你觀察的七項，官網與 OCR 的 L1、L2 維持待資料。自動報告不會將這些人工項目標成通過；詳細入口、步驟與一次回報格式見 [集中驗收清單](docs/acceptance.md)。

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

OCR 分數不足或網站明確回覆驗證碼錯誤時，自動模式會等待設定間隔，重新取得首頁與驗證碼；
每輪都計入 `max_attempts`，驗證碼重試不另設 3 次上限。
查票階段的暫時逾時、連線錯誤與 HTTP 502／503／504 會退避重試。`network_failure_limit` 預設 3，可設 1–100；`max_network_delay_seconds` 預設 30，可設 2–3600 秒。等待依 2、4、8…秒增加至上限，原查詢間隔較長時採原值；也受總查詢次數限制。Qt 進階設定與進度頁提供設定、原因及倒數。
模型故障、未知網站拒絕、HTTP 403／429 仍停止；選車與最終送出訂位不套用上述網路重試。
送出最終訂位前會建立 `booking.local.state.json`；成功時保存訂位代碼，結果不明時保留待確認紀錄。
再次使用同一設定檔訂位會停止，請先至官網確認狀態，再自行處理紀錄，避免重複訂位。

每次開始自動查詢時，會在 `booking.local.runs/<本次執行代碼>/` 保存 `events.jsonl`，
記錄每輪狀態、OCR 模型與分數、各階段耗時。成功後另存 `result.json`，包含訂位代碼、行程、座位、金額與繳費期限。
終端會顯示檔案位置；兩種紀錄皆不寫入身分證、手機或驗證碼，資料夾已由 Git 忽略。
詳見 [結果與執行紀錄](docs/automation.md#結果與執行紀錄)。

完整欄位、無票重查條件與復原方式見 [自動訂位說明](docs/automation.md)。
可在設定檔加入 `"ocr_model": "beta"` 試用另一套內建模型，預設為 `"standard"`；
尚無實站標註資料證明哪套更準，請見 [OCR 模型比較與評估](docs/ocr-evaluation.md)。

## 查看與封存訂位紀錄

Qt 圖形介面可在「我的訂位」選取訂位後按「移至歷史」，確認一次即可準備下一筆，不需手動刪檔或重打代碼。
若訂位後斷線而顯示「結果待確認」，按「處理待確認」開啟官網核對，再勾選確認並保存核對結果。
以上只封存本機紀錄，**官網訂位仍保留**。真正取消須透過介面的官網取消引導，在官網完成取消後再回來確認封存；目前不會代送取消請求。操作說明見 [桌面介面](docs/desktop.md)。

以下指令只處理本機紀錄，不連線、不讀取個資設定，也不會直接啟動訂位：

```powershell
# 查看目前防重送狀態、完整結果與封存紀錄
.\.venv\Scripts\python.exe -m thsr_ticket.main --config booking.local.json --show-bookings

# 以目前紀錄的訂位代碼確認封存（將 YOUR_CODE 換成實際代碼）
.\.venv\Scripts\python.exe -m thsr_ticket.main --config booking.local.json --archive-booking YOUR_CODE
```

封存會把已成功的狀態檔移至 `booking.local.runs/archives/<代碼>/state.json`，保留完整結果，
並解除原狀態檔的防重送阻擋。**這不會取消官網訂位**；請先確認原訂位，再更新行程設定、另行啟動下一筆。
此 CLI 封存指令不接受結果待確認、紀錄損壞或代碼不符的紀錄；待確認請使用上述介面核對流程。

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
- 自動模式的設定檔預設保存明文個資；Qt 可選擇 Windows DPAPI 保護證號與手機，保護後需由同一 Windows 使用者解密，不適合直接跨帳號搬移。
  此選項不會加密整份設定、訂位結果或舊 CLI 歷史。`booking.local.json`、`*.state.json`、`*.task.json`、`*.runs/` 與 `.db/` 已由 Git 忽略；自訂個資檔名也需加入忽略清單。

## 測試與驗證

```powershell
# 安裝開發工具；測試 Qt 時同時保留 requirements-desktop.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 離線測試
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider

# 加入本機 Chrome 操作測試：攔截網站請求，不建立真實訂位
.\.venv\Scripts\python.exe -m pytest -q --browser-tests -p no:cacheprovider

# 程式風格檢查
.\.venv\Scripts\python.exe -m flake8 -j1 --config .config/flake thsr_ticket
```

2026-10-24 最新集中驗證：**534 項通過、1 項實站測試跳過**，Flake8 通過；十項瀏覽器測試已實際執行。本輪增加 41 項範本、日期分類、提醒去重與 Qt 操作回歸，原生 Windows 補驗鍵盤開啟／套用範本及月曆切換。另以真 Chrome 攔截全部請求驗證四種合成管理情境，並完成 10,000 筆 QML 量測、兩套模型載入、100／150% 預覽及三組原生視窗檢查；年月日滾輪亦涵蓋拖曳、滾動、重開、月底及取消。這些不代表實站取消或實際通知點擊已驗收。未加 `--browser-tests` 的一般回歸仍會跳過十項瀏覽器測試。既有 0.4.0 打包／升級證據保留，後續更新只在原始碼；外部驗收見 [專案驗證](docs/verification.md)。
測試涵蓋定時等待、次秒間隔、車次篩選、無票重查、成功停止與訂位結果不明時不重送。
人工 HTML 與本機模擬不能取代實站驗證；Mypy、Pylint 與 CI 尚有待整理項目。
push／PR 的 CI 設有 Linux 基礎測試與 Windows Qt 桌面測試。Windows 使用 `--require-desktop`，缺少桌面測試套件、整個測試模組未執行或桌面測試跳過都會失敗，選用瀏覽器與實站測試仍預設跳過。JUnit 報告保存在 workflow artifact。
本機 Windows 可用 `python -m pytest -q -p no:cacheprovider --require-desktop` 執行同樣檢查；此模式要求完整桌面測試組，不適合只選單一測試。Windows 打包驗證仍是手動 workflow，遠端成功與否需另看 Actions 結果。

若需單獨測試 HTTP 首頁讀取，可執行下列指令；只讀取頁面與驗證碼，不送出訂位：

```powershell
.\.venv\Scripts\python.exe -m pytest thsr_ticket/unittest/test_http_request.py --live -q
```

詳細紀錄：[專案驗證](docs/verification.md)、[瀏覽器與 OCR](docs/browser-ocr.md)。

## 功能對應程式碼

以下是找程式的起點；**每個 Python、QML、PowerShell、建置檔與測試檔的個別用途**均列於 [逐檔索引](docs/file-inventory.md#保留檔案逐項索引)。

| 要理解或修改的功能 | 主要程式碼 |
| --- | --- |
| 桌面啟動與資源載入 | [desktop/__main__.py](thsr_ticket/desktop/__main__.py) |
| 頁面、按鈕、欄位與對話框 | [Main.qml](thsr_ticket/desktop/qml/Main.qml)、[Field.qml](thsr_ticket/desktop/qml/Field.qml) 與同目錄共用元件 |
| 介面事件、設定切換、背景任務 | [desktop/controller.py](thsr_ticket/desktop/controller.py)、[application.py](thsr_ticket/application.py) |
| 設定分頁、診斷及桌面工具 | [SettingsPage.qml](thsr_ticket/desktop/qml/SettingsPage.qml)、[desktop/tools.py](thsr_ticket/desktop/tools.py) |
| 常用行程範本 | [journey_templates.py](thsr_ticket/journey_templates.py)、[desktop/planner.py](thsr_ticket/desktop/planner.py)、[TemplateDialog.qml](thsr_ticket/desktop/qml/TemplateDialog.qml) |
| 月曆、待辦與繳費提醒 | [journey_planning.py](thsr_ticket/journey_planning.py)、[JourneyCalendar.qml](thsr_ticket/desktop/qml/JourneyCalendar.qml)、[AgendaCard.qml](thsr_ticket/desktop/qml/AgendaCard.qml)、[DeadlineDialog.qml](thsr_ticket/desktop/qml/DeadlineDialog.qml) |
| 完整備份、驗證及新位置還原 | [backup.py](thsr_ticket/backup.py)、[desktop/backup.py](thsr_ticket/desktop/backup.py)、[BackupDialog.qml](thsr_ticket/desktop/qml/BackupDialog.qml) |
| 實驗性官網核對與未付款取消 | [official_booking.py](thsr_ticket/official_booking.py)、[booking_management.py](thsr_ticket/remote/booking_management.py)、[desktop/management.py](thsr_ticket/desktop/management.py)、[ManagementDialog.qml](thsr_ticket/desktop/qml/ManagementDialog.qml) |
| 保留期限與永久純查票日誌清理 | [retention.py](thsr_ticket/retention.py)、[desktop/retention.py](thsr_ticket/desktop/retention.py)、[RetentionDialog.qml](thsr_ticket/desktop/qml/RetentionDialog.qml) |
| 設定驗證、排程、查票、重試與訂位 | [automation.py](thsr_ticket/automation.py) |
| 任務摘要、狀態與復原入口 | [task_status.py](thsr_ticket/task_status.py)、[TaskPanel.qml](thsr_ticket/desktop/qml/TaskPanel.qml) |
| 歷史診斷與過濾匯出 | [history_diagnostics.py](thsr_ticket/history_diagnostics.py)、[desktop/history.py](thsr_ticket/desktop/history.py)、[HistoryDialog.qml](thsr_ticket/desktop/qml/HistoryDialog.qml) |
| 可選桌面通知 | [notifications.py](thsr_ticket/desktop/notifications.py)、[preferences.py](thsr_ticket/desktop/preferences.py) |
| 紀錄封存、待確認與人工取消確認 | [booking_records.py](thsr_ticket/booking_records.py) |
| 防止同一設定同時操作、保存結果 | [record_lock.py](thsr_ticket/record_lock.py)、[run_records.py](thsr_ticket/run_records.py) |
| 設定保存、個資保護、最近檔案 | [config_store.py](thsr_ticket/config_store.py)、[preferences.py](thsr_ticket/desktop/preferences.py) |
| 瀏覽器與 HTTP 傳輸 | [browser_request.py](thsr_ticket/remote/browser_request.py)、[native_browser.py](thsr_ticket/remote/native_browser.py)、[http_request.py](thsr_ticket/remote/http_request.py) |
| 網頁車次、訂位結果與錯誤解析 | [avail_trains.py](thsr_ticket/view_model/avail_trains.py)、[booking_result.py](thsr_ticket/view_model/booking_result.py)、[error_feedback.py](thsr_ticket/view_model/error_feedback.py) |
| OCR、圖形標註與離線準確率評估 | [captcha.py](thsr_ticket/captcha.py)、[ocr_benchmark.py](thsr_ticket/ocr_benchmark.py)、[desktop/ocr_lab.py](thsr_ticket/desktop/ocr_lab.py)、[OcrLabDialog.qml](thsr_ticket/desktop/qml/OcrLabDialog.qml) |
| CLI／舊 Tk 入口 | [main.py](thsr_ticket/main.py)、[gui.py](thsr_ticket/gui.py) |
| 版本檢查、EXE 與安裝包 | [updates.py](thsr_ticket/desktop/updates.py)、[TravelDesk.spec](TravelDesk.spec)、[TravelDesk.iss](installer/TravelDesk.iss) |

開發期優先完善介面、資料保留與核心功能；目前已完成單份設定及關聯紀錄的完整備份／還原。安裝包暫緩，待主要流程定案後集中驗收；完整排序與完成條件見 [優化計畫](docs/roadmap.md)。

## 專案來源

本專案基於 [BreezeWhite/THSR-Ticket](https://github.com/BreezeWhite/THSR-Ticket)，此分支新增 Windows 驗證、瀏覽器連線、本機 OCR 與定時自動流程。

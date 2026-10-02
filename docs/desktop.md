# Travel Desk 桌面版

新版以 PySide6 / Qt Quick 實作；原 Tk 介面保留為過渡入口。

## 啟動

專案現有 Windows 環境：

```powershell
.\.venv\windows\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\windows\Scripts\python.exe -m thsr_ticket.desktop
```

重新安裝套件後，`thsr-ticket-gui` 會開啟新版；`thsr-ticket-gui-legacy` 開啟舊版。
原本 `python -m thsr_ticket.gui` 仍是 Tk 版。

## 操作

- **旅程總覽**：下一筆行程與目前任務摘要。
- **新增行程**：選站、日期、時段、票種、身分證及排程；重查間隔與 OCR 模型在「進階設定」。
- **任務進度**：等待倒數、查詢輪數、符合車次與停止；詳細日誌可展開。
- **我的訂位**：車次、座位、金額、期限與代碼。代碼可選取複製。
- **設定**：載入、另存、資料位置及環境檢查。

「只查票」與「自動訂位 · 不付款」會先保存設定並驗證；啟動後不可修改設定或重複啟動。
停止與關閉視窗會等待目前請求與瀏覽器清理結束，不會把已送出的訂位重送或取消。
身分證旁的眼睛可顯示／隱藏；載入設定或啟動任務會重新遮蔽。

## 舊設定與資料位置

首次使用新版請按「載入設定」，選擇既有 `booking.local.json`。
**沿用原檔位置與其 `.state.json`、`.runs/`，不會只複製設定而遺漏防重送紀錄。**
範本需另存才能啟動；目前仍有狀態紀錄時，不允許直接另存以略過阻擋。

新建設定預設存放 Qt 的 AppLocalDataLocation（Windows 為使用者 Local AppData 下的
`THSRTicket/TravelDesk`），下次啟動會載入該位置的設定。
手動載入專案中的設定不會搬移原檔；再次開啟 App 時需再次載入該檔。
安裝目錄只放程式資源，設定與訂位資料不寫在 EXE 旁。

「移至歷史」只封存本機紀錄，官網訂位保留。
送出後斷線，請按「處理待確認」，在官網核對後填入結果並勾選確認。
原始 state 與人工核對結果仍保存於 archives；不確定時請返回，不要重複訂位。

## Windows 發行包

```powershell
.\.venv\windows\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\windows\Scripts\python.exe -m PyInstaller TravelDesk.spec --noconfirm
```

產物為 `dist/TravelDesk/TravelDesk.exe`。分發時需保留整個 `TravelDesk` 資料夾，不能只複製 EXE。
打包設定包含 QML、OCR 模型與 Playwright 驅動；使用者仍需安裝 Chrome。
spec 只加入指定程式資源，不會加入專案中的個人設定、state 或 runs。

可用離線自我檢查核對打包資源：

```powershell
Start-Process -FilePath .\dist\TravelDesk\TravelDesk.exe -ArgumentList '--self-test', 'build/package-smoke.json' -WindowStyle Hidden -Wait
Get-Content build/package-smoke.json
```

自我檢查只使用暫存設定、載入兩套 OCR 模型與啟動 Playwright 驅動，沒有連線官網或送出訂位。
目前為資料夾式發行包；尚未製作簽章安裝程式、自動更新或完成乾淨 Windows 的安裝驗收。

## 驗證紀錄

2026-10-02：184 項離線測試通過、11 項選用測試跳過；Flake8 通過。
測試涵蓋新版欄位驗證、設定與舊狀態關聯、眼睛切換、任務啟停、待確認核對與五頁 QML 載入。
已使用假資料渲染 100%、125%、150% 縮放並檢視畫面；沒有讀取個人設定或送出實際訂位。
本機 EXE 自我檢查通過 QML、standard/beta 模型及 Playwright 驅動載入。

開發者可重現畫面檢查：

```powershell
.\.venv\windows\Scripts\python.exe -m scripts.preview_desktop --scale 1.25
```

輸出位於被 Git 忽略的 `build/preview/`，其中訂位與代碼都是假資料。

## 架構

- `application.py`：GUI 無關的設定轉換、背景工作與合作式停止，Tk 與 Qt 共用。
- `desktop/controller.py`：Qt 屬性／訊號與使用者操作，背景工作不直接更新元件。
- `desktop/qml/`：頁面與共用卡片、輸入欄位、向量圖示、按鈕。
- `automation.py` / `booking_records.py`：訂票核心與狀態紀錄，保留 CLI 相容性。

背景工作仍透過舊核心的 stdout 收集詳細文字日誌；主要階段與車次使用結構化事件。
這是單任務桌面架構，不支援同一程序同時執行多筆任務。

打包規則參考 [PyInstaller spec 官方文件](https://pyinstaller.org/en/stable/spec-files.html)及
[Playwright Python 打包說明](https://playwright.dev/python/docs/library#pyinstaller)。

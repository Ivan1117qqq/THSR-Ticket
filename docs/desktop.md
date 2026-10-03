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

0.3.0 加入時間選擇器、未儲存變更提醒、欄位錯誤提示、錯誤復原入口，以及訂位搜尋、日期／狀態篩選與複製代碼。
「已人工核對」的歷史紀錄會顯示核對結果與時間。網路失敗與訂位結果不明不會自動重送訂位。

「只查票」與「自動訂位 · 不付款」會先保存設定並驗證；啟動後不可修改設定或重複啟動。
停止與關閉視窗會等待目前請求與瀏覽器清理結束，不會把已送出的訂位重送或取消。
身分證旁的眼睛可顯示／隱藏；載入設定或啟動任務會重新遮蔽。

## 舊設定與資料位置

首次使用新版請按「載入設定」，選擇既有 `booking.local.json`。
**沿用原檔位置與其 `.state.json`、`.runs/`，不會只複製設定而遺漏防重送紀錄。**
範本需另存才能啟動；目前仍有狀態紀錄時，不允許直接另存以略過阻擋。

新建設定預設存放 Qt 的 AppLocalDataLocation（Windows 為使用者 Local AppData 下的
`THSRTicket/TravelDesk`），下次啟動會載入該位置的設定。
手動載入專案中的設定不會搬移原檔；App 會在 `preferences.json` 記住原路徑，下次自動載入。
原檔移動或不存在時會提示重新載入，不會自動複製出另一份設定來略過原狀態紀錄。
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
亦提供 Inno Setup 安裝程式：先安裝 Inno Setup 6，再執行 `ISCC.exe installer/TravelDesk.iss`。
產物為 `dist/installer/TravelDesk-Setup-0.3.0.exe`，可選擇桌面捷徑，安裝至目前使用者的 Programs 目錄。
App 執行中會阻擋升級與解除安裝，不會強制結束訂位。解除安裝不刪除使用者設定與訂位資料。
目前依使用者選擇交付**未簽章**安裝包；部分系統可能顯示未識別發行者提示。

## 個資保存

Windows 新設定預設以目前帳號的 DPAPI 保護身分證與手機。舊明文設定仍可載入；
到「設定」勾選保護後按儲存，才會轉換原檔。CLI 與舊 Tk 介面也能讀取受保護的設定。
需要搬到其他電腦時，可先取消保護並儲存成明文；請自行妥善保管。
此保護不涵蓋舊備份、訂位結果檔或程式執行期間的記憶體，也不阻止同一 Windows 帳號下的其他程式存取。
機制參考 [Microsoft DPAPI 文件](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)。

## 更新與發行驗證

「設定 → 檢查更新」會手動查詢專案 GitHub 正式版本；有新版時開啟固定的發行頁。
不會自動下載或執行遠端檔案。更新失敗時原版仍可使用；需要回復時可重新安裝先前保留的版本。
發布前應保留上一版安裝包，且不得以恢復備份為由移除較新的防重送紀錄。

`.github/workflows/desktop-release.yml` 提供手動執行的建置、獨立 runner 啟動及安裝／升級／解除安裝驗證。
此流程只上傳 CI artifacts，不自動發布 GitHub Release；尚未在遠端執行，不能視為乾淨 Windows 驗收已通過。
有簽章憑證後可使用 `scripts/sign_release.ps1`，先簽 EXE，再重建並簽安裝包；私鑰與密碼不要放進 Git。

## 驗證紀錄

0.3.0：194 項離線測試通過、11 項選用測試跳過；Flake8 通過。
測試涵蓋新版欄位驗證、設定與舊狀態關聯、眼睛切換、任務啟停、待確認核對與五頁 QML 載入。
已使用假資料渲染 100%、125%、150% 縮放並檢視畫面；沒有讀取個人設定或送出實際訂位。
本機 EXE 自我檢查通過 QML、standard/beta 模型、Playwright 驅動載入與 DPAPI 個資往返讀寫；清除 Python 環境變數並限制 PATH 後亦可啟動。

2026-10-03 已通過未簽章安裝包的本機驗收：首次安裝、覆蓋升級、已安裝 EXE 自我檢查、解除安裝，以及升級／解除安裝後保留假資料紀錄。App 執行中會阻止安裝與解除安裝。重現指令：

```powershell
.\scripts\test_installer.ps1 -Installer .\dist\installer\TravelDesk-Setup-0.3.0.exe
```

這些檢查使用隔離測試目錄與假資料，沒有操作個人訂位紀錄。仍待獨立乾淨 Windows 環境的 CI 驗收，以及使用者實際透過新版 GUI 進行網站操作；本機驗收不能取代這兩項。

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

背景工作使用專屬輸出 callback，不再全域重導向 stdout；主要階段、車次與完成／錯誤狀態使用結構化事件。
這是單任務桌面架構，不支援同一程序同時執行多筆任務。

打包規則參考 [PyInstaller spec 官方文件](https://pyinstaller.org/en/stable/spec-files.html)及
[Playwright Python 打包說明](https://playwright.dev/python/docs/library#pyinstaller)。

# 逐檔用途、清理依據與保留邊界

更新日期：2026-10-23；現行版本 0.4.0，歷史診斷與通知為尚未打包的原始碼更新。搭配 [完整開發指南](development-guide.md) 與 [後續優化計畫](roadmap.md) 閱讀。下方清理紀錄保留 0.3.1 階段的歷史依據。

## 如何判斷檔案能不能刪

本次檢查 Git 追蹤檔案、Python 匯入、CLI/Tk/Qt 入口、pytest、QML 載入、setuptools package data、PyInstaller spec、Inno Setup、CI 與文件引用。單純「沒有 Python import」不足以刪除 QML、fixtures、圖示或建置腳本。

本索引覆蓋專案維護的原始碼／資源／工具／文件；不逐一列出 `.venv` 的第三方套件，也不讀取個人訂位資料內容。已追蹤但只供相容性測試的舊資料模型明確標註，不假裝是現行主流程必需。

## 本次已移除

| 路徑 | 數量 | 刪除依據 |
| --- | ---: | --- |
| 根目錄 `__init__.py` | 1 | 空白檔；正式套件在 `thsr_ticket/`，根目錄不是應匯入的產品套件。 |
| `thsr_ticket/remote/endpoint_client.py` | 1 | 舊 PTX client，只依賴其獨立 REST 常數；沒有產品入口或測試呼叫。 |
| `thsr_ticket/configs/rest/{__init__,endpoints,station_id}.py` | 3 | 舊 REST 組的常數／套件標記，沒有現行呼叫者；車站資料仍由現行 web 模組提供。 |
| `thsr_ticket/model/json/__init__.py`、`base_response.py` | 2 | 舊 REST response model 根部，沒有現行輸入、輸出或測試路線。 |
| `thsr_ticket/model/json/v1/{__init__,daily_train_info,station_name,stop_sequence,train}.py` | 5 | 僅在該舊模型組內互相引用，未接入產品或測試。 |
| `thsr_ticket/ml/generate_captcha.py`、`image_process.py` | 2 | 早期合成圖片與影像處理實驗；非目前 ddddocr 模型／評估流程，無入口與測試整合，部分依賴未列入安裝契約。 |

共 14 個追蹤檔案。另外移除 `application.QueueWriter` 無呼叫者類別，並從 Flake8 排除清單移除已刪的 `ml` 項目；worker 已直接使用 output callback。

這是依目前倉庫入口與引用確認的清理，不代表已知所有外部使用者是否曾私下 import 舊模組。原始碼仍保留在 Git 的 `262eb99` 及更早歷史，必要時可從該版本取回；本次沒有重寫 Git 歷史。

## 為什麼這些舊東西還保留

- `gui.py`：仍有 `thsr-ticket-gui-legacy` 與 `python -m thsr_ticket.gui` 入口。
- `controller/`、`view/`、`model/db.py`：互動式 CLI 仍會呼叫，部分解析函式與自動流程共用。
- `model/web/`：車站、票數與時間對照仍由 CLI 使用；舊 BookingForm / ConfirmTicket / ConfirmTrain 則保留既有相容性 API 與測試。本次不藉刪除測試來降低維護量，若將來退役應另行遷移 API。
- 多份 requirements：分別是基本、鎖定、自動化、桌面與打包依賴，不是重複備份。
- `scripts/sign_release.ps1`：目前沒有簽章憑證，但它是明確的發行工具，不是無用途殘檔。
- `.config/mypy.ini`、`.config/pylintrc`：makefile 仍引用；它們屬歷史檢查工具，不能宣稱目前全數通過。

## 本機非追蹤內容的用途

| 類別 | 路徑範例 | 處理 |
| --- | --- | --- |
| 個人設定／現有票 | `booking.local.json`、`*.state.json`、`*.runs/` | 保留，未讀取內容；不可按未被 import 判定無用。 |
| Python 環境 | `.venv/` | 保留，是目前測試、啟動及打包所需環境。 |
| 已產生安裝包 | `dist/` | 保留，使用者仍可能安裝／交付；它不是原始碼。 |
| 建置與驗證資料 | `build/` | 保留，包括打包快取、Inno 工具、自我檢查與假資料測試報告；可重建不等於本次無用途。 |
| editable install 中繼資料 | `thsr_ticket.egg-info/` | 保留，可能與目前環境的套件安裝關聯。 |
| 工具快取 | `__pycache__/`、`.mypy_cache/` | 不列為產品原始碼；本次未做全磁碟快取清理，執行測試也會再產生。 |
| 舊 pytest 暫存目錄 | `pytest-cache-files-a7rm50v5/`、`pytest-cache-files-rhm4h093/` | 盤點時存取遭拒；沒有強制接管權限或刪除，亦未當作有效原始碼。 |
| 倉庫與工具資料 | `.git/`、可能的 IDE／代理設定 | 保留；版本歷史不是待清理的業務檔案。 |

## 保留檔案逐項索引

下面列的是清理後維護的檔案快照。後續新增或刪除檔案時，請同步更新本表。

| 檔案 | 用途與保留理由 |
| --- | --- |
| [.config/flake](../.config/flake) | 目前 Flake8 規則，供 make、CI 與人工檢查使用；保留既有 main.py、configs 排除設定。 |
| [.config/mypy.ini](../.config/mypy.ini) | 保留 make check-mypy 使用的歷史型別檢查設定；不宣稱目前全數通過。 |
| [.config/pylintrc](../.config/pylintrc) | 保留 make check-pylint 的歷史規則；不宣稱目前全數通過。 |
| [.github/workflows/desktop-release.yml](../.github/workflows/desktop-release.yml) | 手動執行 Windows 打包與獨立 runner 的產物驗證，不自動發布 Release。 |
| [.github/workflows/pythonpackage.yml](../.github/workflows/pythonpackage.yml) | push／PR 的 Linux 基礎回歸與 Windows Qt 必測工作，保存桌面 JUnit 報告。 |
| [.gitignore](../.gitignore) | 排除 venv、build/dist、個人設定、state/runs 及鎖檔等本機內容。 |
| [README.md](../README.md) | 使用入口、環境建置、文件導覽及功能邊界。 |
| [TravelDesk.spec](../TravelDesk.spec) | PyInstaller 配方，明確收集 QML、圖示、OCR 與 ONNX 執行庫。 |
| [booking.example.json](../booking.example.json) | 可追蹤的設定範例，作為欄位契約與新使用者起點。 |
| [desktop_launcher.py](../desktop_launcher.py) | PyInstaller 的桌面入口，呼叫 Qt main。 |
| [docs/app-architecture.md](../docs/app-architecture.md) | 介面遷移的歷史設計背景，與現行實作區分。 |
| [docs/automation.md](../docs/automation.md) | 設定欄位、排程、自動訂位與命令列操作。 |
| [docs/browser-ocr.md](../docs/browser-ocr.md) | 瀏覽器與 OCR 操作及歷史驗證紀錄。 |
| [docs/desktop.md](../docs/desktop.md) | 現行 Qt 操作、取消引導、資料位置與打包說明。 |
| [docs/development-guide.md](../docs/development-guide.md) | 初學者的完整架構、流程、設計取捨與實作練習。 |
| [docs/file-inventory.md](../docs/file-inventory.md) | 本檔，逐檔盤點、刪除依據與本機資料分類。 |
| [docs/gui.md](../docs/gui.md) | 保留的舊 Tk GUI 操作文件。 |
| [docs/ocr-evaluation.md](../docs/ocr-evaluation.md) | 人工標註、離線模型比較與指標解讀。 |
| [docs/roadmap.md](../docs/roadmap.md) | 0.3.2 功能缺口、優化優先順序、對應程式與驗收條件；不代表已實作。 |
| [docs/verification.md](../docs/verification.md) | 各階段驗證結果與未完成項目；歷史數字不是最新總數。 |
| [installer/TraditionalChinese.isl](../installer/TraditionalChinese.isl) | Inno Setup 使用的繁體中文安裝訊息。 |
| [installer/TravelDesk.iss](../installer/TravelDesk.iss) | Windows 安裝、捷徑、版本及執行中保護規則。 |
| [CHANGELOG.md](../CHANGELOG.md) | 發行版本與功能摘要。 |
| [MANIFEST.in](../MANIFEST.in) | 來源封裝納入依賴清單與桌面資源。 |
| [pyproject.toml](../pyproject.toml) | PEP 517 建置後端與固定 setuptools 版本。 |
| [docs/releasing.md](releasing.md) | 統一版本、依賴分類、建置與隔離安裝升級驗收。 |
| [docs/history-diagnostics.md](history-diagnostics.md) | 歷史任務診斷、匯出範圍、桌面通知操作與背景工作設計。 |
| [docs/desktop-ui.md](desktop-ui.md) | 設定分頁、測試通知、鍵盤操作、頁面與工具服務的分層說明。 |
| [docs/backup.md](backup.md) | 完整備份及新資料夾還原、範圍、個資保護、衝突與中斷處理。 |
| [scripts/release_metadata.py](../scripts/release_metadata.py) | 由單一版本來源產生 Windows 資源、安裝版本、hash 與發行資訊。 |
| [scripts/installer_fixture.py](../scripts/installer_fixture.py) | 產生不同 AppId 的隔離安裝測試包，檢查 payload 版本。 |
| [scripts/build_release.ps1](../scripts/build_release.ps1) | 串接桌面必測、打包、安裝編譯與發行資訊產生。 |
| [thsr_ticket/unittest/test_release_metadata.py](../thsr_ticket/unittest/test_release_metadata.py) | 版本一致性、hash、非法版本與不執行來源內容的測試。 |
| [makefile](../makefile) | 開發命令集合；其中型別與 pylint 舊檢查需另外維護。 |
| [pytest.ini](../pytest.ini) | 測試根目錄與 browser/integration 標記。 |
| [requirements-automation-lock.txt](../requirements-automation-lock.txt) | 引用基礎 lock，固定自動化與 OCR 執行依賴。 |
| [requirements-automation.txt](../requirements-automation.txt) | 選用瀏覽器與 OCR 直接依賴清單。 |
| [requirements-build.txt](../requirements-build.txt) | 引用桌面依賴並固定 PyInstaller 及其建置依賴，不含開發工具。 |
| [requirements-desktop.txt](../requirements-desktop.txt) | 引用自動化 lock 並加入 Qt。 |
| [requirements-lock.txt](../requirements-lock.txt) | 固定基本執行依賴，不含開發工具。 |
| [requirements-dev.txt](../requirements-dev.txt) | 引用基本執行依賴與開發工具 lock。 |
| [requirements-dev-lock.txt](../requirements-dev-lock.txt) | 固定 pytest、Flake8、Mypy、Pylint 與其依賴。 |
| [requirements.txt](../requirements.txt) | setup 的基本執行依賴範圍。 |
| [scripts/build_icon.py](../scripts/build_icon.py) | 從 SVG 產生打包所需 PNG/ICO；由 spec 呼叫。 |
| [scripts/preview_desktop.py](../scripts/preview_desktop.py) | 使用假資料離線渲染頁面、資料管理、歷史診斷、匯出與取消視窗。 |
| [scripts/sign_release.ps1](../scripts/sign_release.ps1) | 未來持有簽章憑證時使用；目前未簽章交付仍保留此發行工具。 |
| [scripts/test_installer.ps1](../scripts/test_installer.ps1) | 隔離安裝、升級、解除安裝及假資料保留驗收。 |
| [setup.py](../setup.py) | Python 套件、版本、package data 與 CLI/Qt/Tk entry points。 |
| [thsr_ticket/__init__.py](../thsr_ticket/__init__.py) | 正式 Python 套件初始化，提供舊 CLI 使用的 MODULE_PATH；不可與根目錄空檔混淆。 |
| [thsr_ticket/application.py](../thsr_ticket/application.py) | Qt/Tk 共用表單轉換、worker、合作式停止與 queue 事件。 |
| [thsr_ticket/automation.py](../thsr_ticket/automation.py) | 設定模型、排程、選車、重試、訂位與防重送核心。 |
| [thsr_ticket/booking_records.py](../thsr_ticket/booking_records.py) | 讀取、封存、待確認核對及人工取消確認；不自動送出官網取消。 |
| [thsr_ticket/captcha.py](../thsr_ticket/captcha.py) | 實際使用的 ddddocr 介面、CTC 候選解析及分數門檻。 |
| [thsr_ticket/config_store.py](../thsr_ticket/config_store.py) | 設定版本檢查、舊格式備份遷移、JSON 原子保存與 Windows DPAPI 欄位保護。 |
| [thsr_ticket/unittest/test_config_store.py](../thsr_ticket/unittest/test_config_store.py) | 舊格式唯讀相容、首次備份、未知版本阻擋與失敗不覆寫測試。 |
| [thsr_ticket/diagnostics.py](../thsr_ticket/diagnostics.py) | 診斷欄位與值的允許清單、事件上限及環境／狀態快照；不匯出原始日誌。 |
| [thsr_ticket/backup.py](../thsr_ticket/backup.py) | 單份設定及關聯紀錄盤點、ZIP 封裝、雜湊／時間驗證及不覆寫還原。 |
| [thsr_ticket/unittest/test_backup.py](../thsr_ticket/unittest/test_backup.py) | 完整備份往返、狀態保留、格式與路徑檢查、衝突、競爭及中斷保護測試。 |
| [thsr_ticket/history_diagnostics.py](../thsr_ticket/history_diagnostics.py) | 過去任務與備份的受限唯讀掃描、環境來源、結果分類及診斷過濾。 |
| [thsr_ticket/unittest/test_history_diagnostics.py](../thsr_ticket/unittest/test_history_diagnostics.py) | 舊紀錄、大型／損壞內容、個資排除、結果未知、取消及背景共用日誌測試。 |
| [thsr_ticket/unittest/test_diagnostics.py](../thsr_ticket/unittest/test_diagnostics.py) | 個資排除、未知型別與數值處理、事件數量及快照獨立性測試。 |
| [thsr_ticket/configs/__init__.py](../thsr_ticket/configs/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/configs/common.py](../thsr_ticket/configs/common.py) | 既有日期、時間選項與票數常數，供模型與互動式 CLI 使用。 |
| [thsr_ticket/configs/web/__init__.py](../thsr_ticket/configs/web/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/configs/web/enums.py](../thsr_ticket/configs/web/enums.py) | 現行網頁流程使用的車站／票種列舉。 |
| [thsr_ticket/configs/web/http_config.py](../thsr_ticket/configs/web/http_config.py) | 網站 URL 與 HTTP 預設參數。 |
| [thsr_ticket/configs/web/param_schema.py](../thsr_ticket/configs/web/param_schema.py) | 現行 Pydantic 表單模型，也保留舊 JSON-schema 模型需要的 schema。 |
| [thsr_ticket/configs/web/parse_avail_train.py](../thsr_ticket/configs/web/parse_avail_train.py) | 車次頁解析選擇條件，供 AvailTrains 使用。 |
| [thsr_ticket/configs/web/parse_html_element.py](../thsr_ticket/configs/web/parse_html_element.py) | 網站 HTML 定位條件，供傳輸與解析器使用。 |
| [thsr_ticket/controller/__init__.py](../thsr_ticket/controller/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/controller/booking_flow.py](../thsr_ticket/controller/booking_flow.py) | 仍可執行的互動式 CLI 主流程。 |
| [thsr_ticket/controller/confirm_ticket_flow.py](../thsr_ticket/controller/confirm_ticket_flow.py) | 互動式乘客確認；member radio 解析也被自動流程重用。 |
| [thsr_ticket/controller/confirm_train_flow.py](../thsr_ticket/controller/confirm_train_flow.py) | 互動式 CLI 的選車步驟。 |
| [thsr_ticket/controller/first_page_flow.py](../thsr_ticket/controller/first_page_flow.py) | 互動式首頁流程；其中動態選項解析函式也被 AutomationRunner 重用。 |
| [thsr_ticket/desktop/__init__.py](../thsr_ticket/desktop/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/desktop/__main__.py](../thsr_ticket/desktop/__main__.py) | Qt 啟動、資源載入、安裝保護 mutex 與隔離 self-test。 |
| [thsr_ticket/desktop/assets/app.svg](../thsr_ticket/desktop/assets/app.svg) | 應用程式向量圖示；Qt 與 icon 建置都使用。 |
| [thsr_ticket/desktop/controller.py](../thsr_ticket/desktop/controller.py) | QML 的 Property/Signal/Slot、任務管理、資料操作及 queue 消費端。 |
| [thsr_ticket/desktop/tools.py](../thsr_ticket/desktop/tools.py) | 桌面診斷、通知偏好／測試、環境與背景更新檢查；唯讀取得任務上下文。 |
| [thsr_ticket/desktop/backup.py](../thsr_ticket/desktop/backup.py) | 完整備份背景工作、檔案選擇、預覽、取消及還原結果狀態。 |
| [thsr_ticket/desktop/preferences.py](../thsr_ticket/desktop/preferences.py) | 保存最近設定路徑與桌面通知開關；各偏好更新時保留其他已知欄位。 |
| [thsr_ticket/desktop/history.py](../thsr_ticket/desktop/history.py) | 歷史診斷背景工作、取消、過期結果丟棄、選取與過濾快照。 |
| [thsr_ticket/desktop/notifications.py](../thsr_ticket/desktop/notifications.py) | 固定通知分類、可用性與開關判斷、系統匣介接及點擊回到頁面。 |
| [thsr_ticket/desktop/single_instance.py](../thsr_ticket/desktop/single_instance.py) | 使用者資料目錄單一實例鎖、本機喚回通道與視窗還原；不接收訂位命令。 |
| [thsr_ticket/unittest/test_single_instance.py](../thsr_ticket/unittest/test_single_instance.py) | 實際子程序重複啟動、強制結束復原、通道失敗與視窗喚回測試。 |
| [thsr_ticket/desktop/qml/AppButton.qml](../thsr_ticket/desktop/qml/AppButton.qml) | 共用按鈕外觀與互動。 |
| [thsr_ticket/desktop/qml/Card.qml](../thsr_ticket/desktop/qml/Card.qml) | 共用卡片容器。 |
| [thsr_ticket/desktop/qml/Field.qml](../thsr_ticket/desktop/qml/Field.qml) | 共用欄位、眼睛遮蔽、日期時間選擇及錯誤提示。 |
| [thsr_ticket/desktop/qml/Main.qml](../thsr_ticket/desktop/qml/Main.qml) | 主視窗框架、導覽、共用操作列與頁面／對話框訊號連接。 |
| [thsr_ticket/desktop/qml/OverviewPage.qml](../thsr_ticket/desktop/qml/OverviewPage.qml) | 旅程總覽、狀態及訂位入口。 |
| [thsr_ticket/desktop/qml/JourneyPage.qml](../thsr_ticket/desktop/qml/JourneyPage.qml) | 行程表單、進階設定與錯誤欄位展開／捲動／聚焦。 |
| [thsr_ticket/desktop/qml/ProgressPage.qml](../thsr_ticket/desktop/qml/ProgressPage.qml) | 執行進度、停止任務及詳細紀錄顯示。 |
| [thsr_ticket/desktop/qml/BookingsPage.qml](../thsr_ticket/desktop/qml/BookingsPage.qml) | 訂位搜尋、篩選、分頁與逐筆操作請求。 |
| [thsr_ticket/desktop/qml/SettingsPage.qml](../thsr_ticket/desktop/qml/SettingsPage.qml) | 一般偏好、資料管理、進階與關於三個分頁及測試通知入口。 |
| [thsr_ticket/desktop/qml/BookingActions.qml](../thsr_ticket/desktop/qml/BookingActions.qml) | 訂位選取、官網取消引導、本機封存及人工核對對話框。 |
| [thsr_ticket/desktop/qml/StorageDialog.qml](../thsr_ticket/desktop/qml/StorageDialog.qml) | 紀錄整理、備份還原、中斷復原及各項操作確認。 |
| [thsr_ticket/desktop/qml/BackupDialog.qml](../thsr_ticket/desktop/qml/BackupDialog.qml) | 完整備份、還原檔案與目的位置預覽、確認及載入入口。 |
| [thsr_ticket/desktop/qml/DiagnosticDialog.qml](../thsr_ticket/desktop/qml/DiagnosticDialog.qml) | 診斷快照預覽及匯出確認。 |
| [thsr_ticket/desktop/qml/UnsavedDialog.qml](../thsr_ticket/desktop/qml/UnsavedDialog.qml) | 載入或關閉前的未儲存變更選擇。 |
| [thsr_ticket/desktop/qml/Caption.qml](../thsr_ticket/desktop/qml/Caption.qml) | 共用輔助文字、顏色及換行樣式。 |
| [thsr_ticket/desktop/qml/Line.qml](../thsr_ticket/desktop/qml/Line.qml) | 共用分隔線。 |
| [thsr_ticket/desktop/qml/SegmentTab.qml](../thsr_ticket/desktop/qml/SegmentTab.qml) | 共用分頁選取、滑過及鍵盤焦點樣式。 |
| [thsr_ticket/desktop/qml/PreferenceSwitch.qml](../thsr_ticket/desktop/qml/PreferenceSwitch.qml) | 共用偏好開關、停用及鍵盤焦點樣式。 |
| [thsr_ticket/desktop/qml/HistoryDialog.qml](../thsr_ticket/desktop/qml/HistoryDialog.qml) | 歷史任務列表、階段與指引、重新讀取／取消及診斷預覽入口。 |
| [thsr_ticket/desktop/qml/NavIcon.qml](../thsr_ticket/desktop/qml/NavIcon.qml) | 側欄圖示元件。 |
| [thsr_ticket/desktop/updates.py](../thsr_ticket/desktop/updates.py) | 手動檢查固定 GitHub release 來源，不自動安裝更新。 |
| [thsr_ticket/gui.py](../thsr_ticket/gui.py) | 舊 Tk GUI；setup 保留入口且有回歸測試，不屬於死碼。 |
| [thsr_ticket/main.py](../thsr_ticket/main.py) | CLI 參數分流、設定驗證、查票、互動式訂位與紀錄管理。 |
| [thsr_ticket/model/__init__.py](../thsr_ticket/model/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/model/db.py](../thsr_ticket/model/db.py) | 互動式 CLI 的 TinyDB 歷史參數，不是新版 state/runs 儲存層。 |
| [thsr_ticket/model/web/__init__.py](../thsr_ticket/model/web/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/model/web/abstract_params.py](../thsr_ticket/model/web/abstract_params.py) | 舊參數類別共同基底；由相容模型與測試使用。 |
| [thsr_ticket/model/web/booking_form/__init__.py](../thsr_ticket/model/web/booking_form/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/model/web/booking_form/booking_form.py](../thsr_ticket/model/web/booking_form/booking_form.py) | 舊 BookingForm API，保留既有相容測試；不是 Qt 自動訂位主模型。 |
| [thsr_ticket/model/web/booking_form/station_mapping.py](../thsr_ticket/model/web/booking_form/station_mapping.py) | 互動式 CLI 顯示仍使用的車站對照表。 |
| [thsr_ticket/model/web/booking_form/ticket_num.py](../thsr_ticket/model/web/booking_form/ticket_num.py) | 互動式 CLI 表單呈現仍使用的票數類別。 |
| [thsr_ticket/model/web/booking_form/time_table.py](../thsr_ticket/model/web/booking_form/time_table.py) | 互動式 CLI 時段呈現。 |
| [thsr_ticket/model/web/confirm_ticket.py](../thsr_ticket/model/web/confirm_ticket.py) | 舊 ConfirmTicket API，由既有相容性測試維護。 |
| [thsr_ticket/model/web/confirm_train.py](../thsr_ticket/model/web/confirm_train.py) | 舊 ConfirmTrain API，由既有相容性測試維護。 |
| [thsr_ticket/ocr_benchmark.py](../thsr_ticket/ocr_benchmark.py) | 有文件與測試的離線 OCR 評估入口，雖非 App 啟動路徑仍有用途。 |
| [thsr_ticket/record_lock.py](../thsr_ticket/record_lock.py) | 跨程序操作鎖，序列化同一設定的訂位與封存。 |
| [thsr_ticket/desktop/storage.py](../thsr_ticket/desktop/storage.py) | 背景紀錄掃描、取消、日期篩選、勾選與備份批次管理。 |
| [thsr_ticket/record_schema.py](../thsr_ticket/record_schema.py) | 訂位紀錄版本驗證與舊格式唯讀相容。 |
| [thsr_ticket/record_storage.py](../thsr_ticket/record_storage.py) | 歷史執行紀錄預覽、可還原整理與備份搜尋。 |
| [thsr_ticket/storage_journal.py](../thsr_ticket/storage_journal.py) | 操作清單寫入、未完成批次偵測、預檢與中斷復原。 |
| [thsr_ticket/storage_errors.py](../thsr_ticket/storage_errors.py) | 紀錄操作錯誤分類、固定訊息及處理指引。 |
| [thsr_ticket/scan_report.py](../thsr_ticket/scan_report.py) | 掃描統計、固定略過原因與取消協定。 |
| [thsr_ticket/desktop/storage_model.py](../thsr_ticket/desktop/storage_model.py) | Qt 清單資料角色、逐列勾選更新與選取容量統計。 |
| [thsr_ticket/desktop/record_loader.py](../thsr_ticket/desktop/record_loader.py) | 訂位背景讀取與搜尋索引準備、合併刷新、取消及過期快照丟棄。 |
| [thsr_ticket/unittest/test_record_scanning.py](../thsr_ticket/unittest/test_record_scanning.py) | 掃描部分失敗、所選紀錄驗證與結果保留測試。 |
| [scripts/benchmark_records.py](../scripts/benchmark_records.py) | 使用暫存假資料量測掃描、整理、背景載入與 Qt 模型更新。 |
| [thsr_ticket/unittest/test_storage_recovery.py](../thsr_ticket/unittest/test_storage_recovery.py) | 程序中斷、可重入復原、內容衝突與清單失敗測試。 |
| [thsr_ticket/unittest/test_record_storage.py](../thsr_ticket/unittest/test_record_storage.py) | 紀錄版本、防重送保護及整理還原測試。 |
| [docs/record-storage.md](record-storage.md) | 紀錄整理操作、格式契約與復原限制。 |
| [thsr_ticket/remote/__init__.py](../thsr_ticket/remote/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/remote/browser_request.py](../thsr_ticket/remote/browser_request.py) | Playwright/Chrome 傳輸，動態填表及頁面快照。 |
| [thsr_ticket/remote/http_request.py](../thsr_ticket/remote/http_request.py) | requests 傳輸、表單保存及同站 URL 驗證；也供瀏覽器繼承。 |
| [thsr_ticket/remote/native_browser.py](../thsr_ticket/remote/native_browser.py) | 尋找 Chrome/Edge、獨立 profile、等待程序及有限清理重試；每次刪除前核對精確所有權與路徑。 |
| [thsr_ticket/run_records.py](../thsr_ticket/run_records.py) | 原子 JSON、事件 JSONL、成功結果與事件通知。 |
| [thsr_ticket/unittest/conftest.py](../thsr_ticket/unittest/conftest.py) | pytest 共用選項；控制 --live／--browser-tests，並以 --require-desktop 阻擋桌面套件缺測或跳過。 |
| [thsr_ticket/unittest/test_desktop_gate.py](../thsr_ticket/unittest/test_desktop_gate.py) | 桌面必測機制的成功、缺測、跳過與錯誤狀態回歸。 |
| [thsr_ticket/unittest/fixtures/booking.html](../thsr_ticket/unittest/fixtures/booking.html) | 離線網站 HTML 樣本：首頁；測試讀取，不是可刪的下載快取。 |
| [thsr_ticket/unittest/fixtures/confirmation.html](../thsr_ticket/unittest/fixtures/confirmation.html) | 離線網站 HTML 樣本：乘客確認頁；測試讀取，不是可刪的下載快取。 |
| [thsr_ticket/unittest/fixtures/result.html](../thsr_ticket/unittest/fixtures/result.html) | 離線網站 HTML 樣本：訂位結果頁；測試讀取，不是可刪的下載快取。 |
| [thsr_ticket/unittest/fixtures/trains.html](../thsr_ticket/unittest/fixtures/trains.html) | 離線網站 HTML 樣本：車次頁；測試讀取，不是可刪的下載快取。 |
| [thsr_ticket/unittest/model/test_booking_form.py](../thsr_ticket/unittest/model/test_booking_form.py) | 舊 BookingForm API 驗證與相容性。 |
| [thsr_ticket/unittest/model/test_confirm_ticket.py](../thsr_ticket/unittest/model/test_confirm_ticket.py) | 舊 ConfirmTicket API 相容性。 |
| [thsr_ticket/unittest/model/test_confirm_train.py](../thsr_ticket/unittest/model/test_confirm_train.py) | 舊 ConfirmTrain API 相容性。 |
| [thsr_ticket/unittest/test_automation.py](../thsr_ticket/unittest/test_automation.py) | 排程、選車、OCR/網路重試及最終送出防重送。 |
| [thsr_ticket/unittest/test_booking_records.py](../thsr_ticket/unittest/test_booking_records.py) | 紀錄查看、封存、人工核對、鎖及 stale 保護。 |
| [thsr_ticket/unittest/test_browser_request.py](../thsr_ticket/unittest/test_browser_request.py) | 瀏覽器填表、圖片與同站傳輸；需 --browser-tests。 |
| [thsr_ticket/unittest/test_captcha.py](../thsr_ticket/unittest/test_captcha.py) | OCR 候選、分數門檻、異常與延遲載入。 |
| [thsr_ticket/unittest/test_current_flow.py](../thsr_ticket/unittest/test_current_flow.py) | 網站 fixtures、互動式流程、模型與選用實站檢查。 |
| [thsr_ticket/unittest/test_desktop.py](../thsr_ticket/unittest/test_desktop.py) | Qt controller、設定、紀錄操作與 QML 畫面。 |
| [thsr_ticket/unittest/test_desktop_acceptance.py](../thsr_ticket/unittest/test_desktop_acceptance.py) | 真實 worker/runner 搭配假網站的端到端離線流程。 |
| [thsr_ticket/unittest/test_desktop_release.py](../thsr_ticket/unittest/test_desktop_release.py) | DPAPI 與手動版本檢查。 |
| [thsr_ticket/unittest/test_gui.py](../thsr_ticket/unittest/test_gui.py) | 舊 Tk 與共用 GUI 工作流程相容性。 |
| [thsr_ticket/unittest/test_http_request.py](../thsr_ticket/unittest/test_http_request.py) | HTTP session、動態欄位、網址及錯誤處理。 |
| [thsr_ticket/unittest/test_native_browser.py](../thsr_ticket/unittest/test_native_browser.py) | 專用瀏覽器 CDP 退出、資源關閉、暫存鎖定重試上限、精確所有權與每次重查路徑。 |
| [thsr_ticket/unittest/test_ocr_benchmark.py](../thsr_ticket/unittest/test_ocr_benchmark.py) | 標註輸入驗證與評估指標。 |
| [thsr_ticket/unittest/test_run_records.py](../thsr_ticket/unittest/test_run_records.py) | 事件、結果、保存失敗及敏感資料輸出邊界。 |
| [thsr_ticket/version.py](../thsr_ticket/version.py) | Python 套件與桌面版本來源；Windows 資源另有對應版本需同步。 |
| [thsr_ticket/view/__init__.py](../thsr_ticket/view/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/view/common.py](../thsr_ticket/view/common.py) | 互動式 CLI 的歷史選擇呈現。 |
| [thsr_ticket/view/input_utils.py](../thsr_ticket/view/input_utils.py) | 互動式輸入驗證，包含整數範圍等規則。 |
| [thsr_ticket/view/web/__init__.py](../thsr_ticket/view/web/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/view/web/abstract_show.py](../thsr_ticket/view/web/abstract_show.py) | CLI 顯示層基底。 |
| [thsr_ticket/view/web/booking_form_info.py](../thsr_ticket/view/web/booking_form_info.py) | CLI 行程輸入與呈現。 |
| [thsr_ticket/view/web/confirm_ticket_info.py](../thsr_ticket/view/web/confirm_ticket_info.py) | CLI 乘客資料確認。 |
| [thsr_ticket/view/web/show_avail_trains.py](../thsr_ticket/view/web/show_avail_trains.py) | CLI 車次清單與選擇。 |
| [thsr_ticket/view/web/show_booking_result.py](../thsr_ticket/view/web/show_booking_result.py) | 訂位結果格式化，支援 worker 專屬 output callback。 |
| [thsr_ticket/view/web/show_error_msg.py](../thsr_ticket/view/web/show_error_msg.py) | 互動式 CLI 網站錯誤呈現。 |
| [thsr_ticket/view_model/__init__.py](../thsr_ticket/view_model/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/view_model/abstract_view_model.py](../thsr_ticket/view_model/abstract_view_model.py) | HTML 解析共同基底。 |
| [thsr_ticket/view_model/avail_trains.py](../thsr_ticket/view_model/avail_trains.py) | 從網站 HTML 解析可選車次。 |
| [thsr_ticket/view_model/booking_result.py](../thsr_ticket/view_model/booking_result.py) | 從網站 HTML 解析訂位代碼、行程、座位及價款。 |
| [thsr_ticket/view_model/error_feedback.py](../thsr_ticket/view_model/error_feedback.py) | 解析網站錯誤訊息區塊。 |
| [thsr_ticket/task_status.py](../thsr_ticket/task_status.py) | 0.3.2 的有限欄位任務摘要與純函式狀態判定；訂位 state 優先，不自動重送。 |
| [thsr_ticket/desktop/qml/TaskPanel.qml](../thsr_ticket/desktop/qml/TaskPanel.qml) | 首頁與進度頁共用狀態卡、階段與復原入口。 |
| [thsr_ticket/unittest/test_task_status.py](../thsr_ticket/unittest/test_task_status.py) | 狀態優先序、損壞資料、摘要欄位限制與復原路由測試。 |

原 `installer/version_info.txt` 已由 `build/release/version_info.txt` 產物取代，不再維護第二份版本來源。設定旁的 `*.task.json` 與 `*.runs.operations/` 均已加入 Git 忽略清單；不取代原有防重送紀錄。

### 六項優化新增檔案

| 檔案 | 功能與保留理由 |
| --- | --- |
| [docs/booking-management.md](booking-management.md) | 實驗性官網核對／取消操作、命令佇列、持久化、來源契約與實站驗收邊界。 |
| [docs/optimization-audit.md](optimization-audit.md) | 六項需求逐項交付、入口、重試規則、永久清理與未完成驗收確認。 |
| [thsr_ticket/official_booking.py](../thsr_ticket/official_booking.py) | 官網結構化狀態與單程行程核對，查詢／取消證據、指紋及封存。 |
| [thsr_ticket/remote/booking_management.py](../thsr_ticket/remote/booking_management.py) | 已觀察的查詢表單、圖片與換圖，以及精確管理按鈕、來源檢查與不重試取消。 |
| [thsr_ticket/desktop/management.py](../thsr_ticket/desktop/management.py) | 擁有瀏覽器的單一背景執行緒、命令／結果佇列、確認期限及結束等待。 |
| [thsr_ticket/desktop/jobs.py](../thsr_ticket/desktop/jobs.py) | 清理與 OCR 共用背景工作、取消、錯誤回饋及主執行緒取回結果。 |
| [thsr_ticket/retention.py](../thsr_ticket/retention.py) | 過期純查票日誌預覽、狀態與雜湊保護、逐檔永久刪除及稽核。 |
| [thsr_ticket/desktop/retention.py](../thsr_ticket/desktop/retention.py) | 保留天數、固定預覽、明確確認、設定切換保護及清理結果摘要。 |
| [thsr_ticket/desktop/ocr_lab.py](../thsr_ticket/desktop/ocr_lab.py) | 圖片選取、人工標註保存、兩模型比較、取消及去除檔名的統計匯出。 |
| [thsr_ticket/desktop/qml/ManagementDialog.qml](../thsr_ticket/desktop/qml/ManagementDialog.qml) | 查詢驗證碼、官網結果、取消核對／勾選確認與停止入口。 |
| [thsr_ticket/desktop/qml/RetentionDialog.qml](../thsr_ticket/desktop/qml/RetentionDialog.qml) | 保留期限、容量與清單預覽、永久刪除確認及忙碌回饋。 |
| [thsr_ticket/desktop/qml/OcrLabDialog.qml](../thsr_ticket/desktop/qml/OcrLabDialog.qml) | 圖片與人工標籤、評估門檻、模型指標、匯出及手動選用模型。 |
| [thsr_ticket/unittest/test_official_booking.py](../thsr_ticket/unittest/test_official_booking.py) | 明確狀態、方向／車次／日期核對、取消證據、待確認同步與保存失敗。 |
| [thsr_ticket/unittest/test_retention.py](../thsr_ticket/unittest/test_retention.py) | 保留範圍、資料變更、狀態阻擋、稽核失敗與部分清理測試。 |
| [thsr_ticket/unittest/test_feature_desktop.py](../thsr_ticket/unittest/test_feature_desktop.py) | 背景管理工作階段、實際 QML 同意門檻、清理、OCR、倒數與大量資料分頁測試。 |
| [scripts/benchmark_desktop.py](../scripts/benchmark_desktop.py) | 真 QML 假資料卡片數／更新／心跳量測，以及大型日誌及超大單行驗證。 |
| [scripts/verify_management_transport.py](../scripts/verify_management_transport.py) | 真 Chrome 全請求攔截，驗證合成查詢、原生確認、取消、付款／外站阻擋與斷線不重送。 |

### 固定範圍收尾新增檔案

| 檔案 | 功能與保留理由 |
| --- | --- |
| [thsr_ticket/record_search.py](../thsr_ticket/record_search.py) | 每份顯示快照的正規化搜尋文件、目前紀錄數、最多八組篩選快取與每頁 25 筆結果；不讀寫訂位。 |
| [thsr_ticket/unittest/test_record_search.py](../thsr_ticket/unittest/test_record_search.py) | 大小寫／前後空白、複合篩選、頁碼界線、快取重用與淘汰、新快照及建立中取消。 |
| [scripts/verify_desktop_session.py](../scripts/verify_desktop_session.py) | Windows 原生 Qt 隔離視窗：縮放、最小化／最大化、鍵盤、焦點、可存取名稱及選用本機測試通知；不代替人工通知點擊與螢幕閱讀器驗收。 |

`test_feature_desktop.py` 同時補驗背景索引直接交接、替換快照使快取失效，以及真 QML 輸入延遲／Enter／清空。`test_single_instance.py` 補真 QQuickWindow 的狀態測試。`benchmark_desktop.py` 補索引、非空白搜尋、快取換頁及連續輸入量測，完整證據見 [驗證紀錄](verification.md)。

### 集中驗收工具

| 檔案 | 功能與保留理由 |
| --- | --- |
| [docs/acceptance.md](acceptance.md) | 一次執行方式、七項本機操作、兩項待資料驗收、通過條件及一次回報格式。 |
| [scripts/verify_acceptance.py](../scripts/verify_acceptance.py) | 集中執行測試、lint、瀏覽器合成流程、自我檢查、量測、預覽及選用原生驗證；核對報告、非預期跳過、程式指紋與文件索引，生成新的一份 JSON／Markdown 報告。 |
| [scripts/review_desktop.py](../scripts/review_desktop.py) | 建立獨立假資料與偏好資料夾、可操作的 Qt 驗收視窗、讀寫位置限制及真實訂位動作阻擋。 |
| [thsr_ticket/desktop/qml/DatePicker.qml](../thsr_ticket/desktop/qml/DatePicker.qml) | 可上下拖曳、滾動與鍵盤操作的年月日選擇器；閏年／月底調整、視圖對齊及獨立取消／套用。 |
| [thsr_ticket/unittest/test_acceptance_tools.py](../thsr_ticket/unittest/test_acceptance_tools.py) | 假資料、既有檔案不覆寫、無效訂票設定、JUnit 跳過／失敗、必要產物、來源指紋與人工狀態不誤報通過。 |

`test_feature_desktop.py` 補驗隔離視窗的 Qt 指令不啟動 worker、不開官網，以及不能載入或改寫外部設定。`conftest.py`／`test_desktop_gate.py` 將這個新增功能測試模組納入必測；Windows CI 的 Flake8 改為涵蓋整個 scripts 目錄。

日期回歸同樣位於 `test_feature_desktop.py`，涵蓋年月日三欄滾動方向、拖曳、閏年與月底、重開選取、取消及時間保留。`verify_desktop_session.py` 補實際 Windows 的相同操作及日期畫面擷取；`preview_desktop.py` 補搭車／啟動日期的 100／150% 預覽。

## 2026-10-24 行程範本與提醒

| 檔案 | 用途 |
| --- | --- |
| [docs/journey-planner.md](journey-planner.md) | 範本操作、月曆、繳費提醒、資料範圍及程式設計。 |
| [thsr_ticket/journey_templates.py](../thsr_ticket/journey_templates.py) | 非個資欄位允許清單、範本驗證、版本與原子保存。 |
| [thsr_ticket/journey_planning.py](../thsr_ticket/journey_planning.py) | 明確日期／期限解析、付款待辦分類及有上限的月曆索引。 |
| [thsr_ticket/desktop/planner.py](../thsr_ticket/desktop/planner.py) | Qt 範本指令、提醒偏好、手動期限、跨重開去重及首頁模型。 |
| [thsr_ticket/desktop/qml/TemplateDialog.qml](../thsr_ticket/desktop/qml/TemplateDialog.qml) | 範本新增、預覽、套用、重新命名、複製、更新與移除。 |
| [thsr_ticket/desktop/qml/DeadlineDialog.qml](../thsr_ticket/desktop/qml/DeadlineDialog.qml) | 人工核對完整本機期限、年月日選取與保存同意。 |
| [thsr_ticket/desktop/qml/JourneyCalendar.qml](../thsr_ticket/desktop/qml/JourneyCalendar.qml) | 月份切換、日期標記及當日有上限的行程列表。 |
| [thsr_ticket/desktop/qml/AgendaCard.qml](../thsr_ticket/desktop/qml/AgendaCard.qml) | 繳費／核對待辦、剩餘時間及期限設定入口。 |
| [thsr_ticket/unittest/test_journey_planning.py](../thsr_ticket/unittest/test_journey_planning.py) | 範本欄位排除、損壞保留、日期歧義、狀態分類與月曆上限。 |
| [thsr_ticket/unittest/test_planner_desktop.py](../thsr_ticket/unittest/test_planner_desktop.py) | Qt 範本與期限實際操作、防重送不變、通知去重與偏好保存。 |

既有 `record_loader.py` 在背景準備行程索引；`controller.py` 僅作資料與訊號交接；`preferences.py` 保存新增提醒選項。`preview_desktop.py` 補月曆、範本與提醒視窗，`verify_desktop_session.py` 補原生鍵盤操作；桌面必測包含新 Qt 測試模組。

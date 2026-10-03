# 逐檔用途、清理依據與保留邊界

盤點日期：2026-10-03；基準版本 0.3.1。搭配 [完整開發指南](development-guide.md) 閱讀。

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
| [.github/workflows/pythonpackage.yml](../.github/workflows/pythonpackage.yml) | Python 回歸 CI：安裝依賴、格式與測試。 |
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
| [docs/verification.md](../docs/verification.md) | 各階段驗證結果與未完成項目；歷史數字不是最新總數。 |
| [installer/TraditionalChinese.isl](../installer/TraditionalChinese.isl) | Inno Setup 使用的繁體中文安裝訊息。 |
| [installer/TravelDesk.iss](../installer/TravelDesk.iss) | Windows 安裝、捷徑、版本及執行中保護規則。 |
| [installer/version_info.txt](../installer/version_info.txt) | PyInstaller 引用的 Windows EXE 版本資源。 |
| [makefile](../makefile) | 開發命令集合；其中型別與 pylint 舊檢查需另外維護。 |
| [pytest.ini](../pytest.ini) | 測試根目錄與 browser/integration 標記。 |
| [requirements-automation-lock.txt](../requirements-automation-lock.txt) | 引用基礎 lock，固定自動化與 OCR 執行依賴。 |
| [requirements-automation.txt](../requirements-automation.txt) | 選用瀏覽器與 OCR 直接依賴清單。 |
| [requirements-build.txt](../requirements-build.txt) | 引用桌面依賴並加入 PyInstaller。 |
| [requirements-desktop.txt](../requirements-desktop.txt) | 引用自動化 lock 並加入 Qt。 |
| [requirements-lock.txt](../requirements-lock.txt) | 固定基礎環境版本，包含測試與檢查工具。 |
| [requirements.txt](../requirements.txt) | setup 的基本依賴範圍，目前仍包含開發工具。 |
| [scripts/build_icon.py](../scripts/build_icon.py) | 從 SVG 產生打包所需 PNG/ICO；由 spec 呼叫。 |
| [scripts/preview_desktop.py](../scripts/preview_desktop.py) | 使用假資料離線渲染頁面與取消視窗。 |
| [scripts/sign_release.ps1](../scripts/sign_release.ps1) | 未來持有簽章憑證時使用；目前未簽章交付仍保留此發行工具。 |
| [scripts/test_installer.ps1](../scripts/test_installer.ps1) | 隔離安裝、升級、解除安裝及假資料保留驗收。 |
| [setup.py](../setup.py) | Python 套件、版本、package data 與 CLI/Qt/Tk entry points。 |
| [thsr_ticket/__init__.py](../thsr_ticket/__init__.py) | 正式 Python 套件初始化，提供舊 CLI 使用的 MODULE_PATH；不可與根目錄空檔混淆。 |
| [thsr_ticket/application.py](../thsr_ticket/application.py) | Qt/Tk 共用表單轉換、worker、合作式停止與 queue 事件。 |
| [thsr_ticket/automation.py](../thsr_ticket/automation.py) | 設定模型、排程、選車、重試、訂位與防重送核心。 |
| [thsr_ticket/booking_records.py](../thsr_ticket/booking_records.py) | 讀取、封存、待確認核對及人工取消確認；不自動送出官網取消。 |
| [thsr_ticket/captcha.py](../thsr_ticket/captcha.py) | 實際使用的 ddddocr 介面、CTC 候選解析及分數門檻。 |
| [thsr_ticket/config_store.py](../thsr_ticket/config_store.py) | 設定 JSON 原子保存與 Windows DPAPI 欄位保護。 |
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
| [thsr_ticket/desktop/preferences.py](../thsr_ticket/desktop/preferences.py) | 只保存最近設定路徑的桌面偏好。 |
| [thsr_ticket/desktop/qml/AppButton.qml](../thsr_ticket/desktop/qml/AppButton.qml) | 共用按鈕外觀與互動。 |
| [thsr_ticket/desktop/qml/Card.qml](../thsr_ticket/desktop/qml/Card.qml) | 共用卡片容器。 |
| [thsr_ticket/desktop/qml/Field.qml](../thsr_ticket/desktop/qml/Field.qml) | 共用欄位、眼睛遮蔽、日期時間選擇及錯誤提示。 |
| [thsr_ticket/desktop/qml/Main.qml](../thsr_ticket/desktop/qml/Main.qml) | 主視窗、頁面、導覽、紀錄與確認對話框。 |
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
| [thsr_ticket/remote/__init__.py](../thsr_ticket/remote/__init__.py) | 保留套件標記／初始化；Python 匯入與 setuptools 套件發現需要整體判斷，不因內容少就刪除。 |
| [thsr_ticket/remote/browser_request.py](../thsr_ticket/remote/browser_request.py) | Playwright/Chrome 傳輸，動態填表及頁面快照。 |
| [thsr_ticket/remote/http_request.py](../thsr_ticket/remote/http_request.py) | requests 傳輸、表單保存及同站 URL 驗證；也供瀏覽器繼承。 |
| [thsr_ticket/remote/native_browser.py](../thsr_ticket/remote/native_browser.py) | 尋找 Chrome/Edge、獨立 profile 與程序清理。 |
| [thsr_ticket/run_records.py](../thsr_ticket/run_records.py) | 原子 JSON、事件 JSONL、成功結果與事件通知。 |
| [thsr_ticket/unittest/conftest.py](../thsr_ticket/unittest/conftest.py) | pytest 共用選項，控制 --live 與 --browser-tests 的明確啟用。 |
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
| [thsr_ticket/unittest/test_native_browser.py](../thsr_ticket/unittest/test_native_browser.py) | 瀏覽器定位、程序及臨時 profile 清理。 |
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

0.3.2 增補後，本表共 125 個檔案。設定旁的 `*.task.json` 為本機任務摘要，已加入 Git 忽略清單；不保存個資，也不取代原有防重送紀錄。

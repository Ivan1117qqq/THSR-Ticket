# 後續優化與驗收計畫

檢查日期：2026-10-03；依據倉庫 0.3.2 原始碼、測試與建置設定。以下是尚待完成的工作，不是已發布功能。本次更新文件，沒有更動訂位行為，也沒有操作真實訂位。

## 現況判斷

目前已具備 Qt 桌面介面、設定保存、排程查票、自動訂位、查票暫時斷線重試、防重送、結果封存、人工核對與取消引導，以及未簽章 Windows 安裝包。較優先的缺口是持續驗證、跨視窗任務協調、診斷與版本遷移，而非繼續增加首頁按鈕。

取消引導仍須在官網完成取消；本機封存不取消票。任務摘要只協助重開程式後理解狀態，不會恢復工作，也不是跨程序即時監控。已存在的訂位狀態檔仍優先阻擋再次送出。

## 建議依序進行

| 順序 | 現況與待做工作 | 對應程式／設定 | 完成條件 |
| --- | --- | --- | --- |
| 1 | 補齊持續桌面回歸。一般 push 工作只安裝基礎依賴；Windows 桌面工作需手動觸發。 | [Python CI](../.github/workflows/pythonpackage.yml)、[桌面 CI](../.github/workflows/desktop-release.yml)、[桌面測試](../thsr_ticket/unittest/test_desktop.py) | PR／push 有 Windows Qt 離線測試；未安裝 Qt 造成的跳過不可被當成桌面通過；發布前留存打包、自我檢查與安裝升級報告。 |
| 2 | 完成新版 Qt 實站與乾淨 Windows 發行驗收。已有本機測試，但不能以離線 HTML 模擬代表網站相容。 | [驗證紀錄](verification.md)、[安裝測試腳本](../scripts/test_installer.ps1) | 記錄 OS、瀏覽器、版本、執行步驟與結果；先驗查票與停止，再由使用者明確授權測試真實訂位／取消；新版本安裝、升級、解除安裝及資料保留均有證據。 |
| 3 | 協調多視窗／多程序。現有 mutex 用於安裝保護，未據此禁止第二個 App；操作鎖只涵蓋同一設定。 | [桌面入口](../thsr_ticket/desktop/__main__.py)、[操作鎖](../thsr_ticket/record_lock.py)、[任務狀態](../thsr_ticket/task_status.py) | 選定單一實例或明確的任務擁有者設計；第二次開啟能提示／切回原視窗；崩潰後可復原，且不能因摘要過期就重新送出待確認訂位。不同設定的任務政策需明訂。 |
| 4 | 增加介面內的診斷匯出。已有 events.jsonl 與結果，但使用者仍需自行找檔案。 | [執行紀錄](../thsr_ticket/run_records.py)、[桌面 controller](../thsr_ticket/desktop/controller.py) | 一鍵匯出版本、平台、錯誤類型及必要階段資訊；匯出前可預覽；移除證號、手機、訂位代碼、個人路徑與網頁原文；使用假資料測試遮蔽。 |
| 5 | 建立設定／紀錄版本與遷移契約。現在依賴現行 JSON 結構，尚無完整跨版本遷移流程。 | [設定儲存](../thsr_ticket/config_store.py)、[自動設定模型](../thsr_ticket/automation.py)、[訂位紀錄](../thsr_ticket/booking_records.py) | 舊版本設定可在備份後遷移；較新未知版本可讀性失敗時清楚提示且不覆寫；不丟失待確認狀態；DPAPI 跨帳號不可解密時有可理解的操作指引。 |
| 6 | 提供資料保留與清理介面。已有逐筆封存，但尚無完整的容量、保留期限與批次清理政策。 | [訂位紀錄](../thsr_ticket/booking_records.py)、[執行紀錄](../thsr_ticket/run_records.py)、[主畫面](../thsr_ticket/desktop/qml/Main.qml) | 先顯示可清理數量與範圍，再由使用者確認；不得刪除執行中的紀錄、未解決的防重送狀態；本機清理與官網取消文字清楚區分。 |
| 7 | 拆分大型畫面與 controller，完善鍵盤與顯示比例體驗。已有 Field、Card、TaskPanel，但多頁與對話框仍集中。 | [Main.qml](../thsr_ticket/desktop/qml/Main.qml)、[controller.py](../thsr_ticket/desktop/controller.py)、[預覽工具](../scripts/preview_desktop.py) | 按頁面拆分且共用狀態來源；鍵盤焦點、Tab 順序、欄位錯誤、遮蔽切換一致；100／125／150% 顯示比例與長文字無遮擋；維持原有防重送測試。 |
| 8 | 分離產品與開發依賴，統一版本來源。基礎 requirements 仍包含測試工具；Python、Windows 資源、安裝腳本與 workflow 都有版本資訊。 | [requirements.txt](../requirements.txt)、[version.py](../thsr_ticket/version.py)、[版本資源](../installer/version_info.txt)、[安裝腳本](../installer/TravelDesk.iss) | 乾淨環境可分別安裝產品／開發依賴；版本可產生或自動檢查一致性；打包與啟動驗證不退步。 |
| 9 | 完整化發行與更新流程。現在只有手動版本檢查與本機未簽章安裝包。 | [更新檢查](../thsr_ticket/desktop/updates.py)、[簽章腳本](../scripts/sign_release.ps1)、[桌面 CI](../.github/workflows/desktop-release.yml) | 固定版本產物、雜湊、變更紀錄與驗收報告可對應；未持有憑證時清楚標示未簽章；未來取得憑證再加入簽章驗證。自動更新應另行設計失敗回復與完整性驗證。 |
| 10 | 以標註資料評估 OCR，再決定是否調整模型。standard／beta 的分數不能當成真實準確率。 | [辨識器](../thsr_ticket/captcha.py)、[評估工具](../thsr_ticket/ocr_benchmark.py)、[評估說明](ocr-evaluation.md) | 在獨立的人工標註資料上比較整串正確率、接受率與延遲；先保留基準，再決定模型及門檻；不能用提高重試頻率替代準確率證據。 |

## 需要另行定義範圍的功能

- **程式直接取消官網訂位**：目前沒有實作。需先釐清查詢、取消確認、結果未知與人工復原流程；不可把本機移除紀錄當成官網取消成功。任何真實取消都需由使用者確認特定訂位。
- **來回票、會員及其他證件**：涉及設定模型、網站表單、結果解析與所有操作介面；不能只增加幾個 UI 欄位。
- **多行程並行**：先完成任務協調與防重複策略，否則不同設定仍可能送出重複需求。
- **任務完成通知**：可先設計本機桌面通知；郵件或通訊服務另涉及憑證儲存、收件對象與發送授權。

## 本次檢查範圍與維護方式

本次修正 README 的重試條件、Qt 紀錄頁名稱、個資保護描述、安裝包取得方式與驗證數字，新增功能到程式碼的導覽。完整逐檔用途位於 [檔案索引](file-inventory.md)，執行流程與設計理由位於 [開發指南](development-guide.md)。

本次沒有宣稱遠端 CI 已通過，也沒有讀取個人設定或訂位資料。新增功能時，請同步更新操作文件、對應的檔案用途、驗收證據與本表狀態；完成後移入驗證紀錄，避免待辦與已完成功能混在一起。

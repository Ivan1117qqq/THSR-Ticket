# 瀏覽器連線與本機 OCR

本次修改針對 HTTP 訂票首頁逾時，以及手動輸入驗證碼造成的操作成本。
以下區分已通過的測試與尚未完成的實站驗證。

此頁保留瀏覽器與 OCR 階段的 85 項測試紀錄。後續新增的定時自動模式與最新 119 項測試結果，
請見 [自動訂位說明](automation.md) 與 [專案驗證紀錄](verification.md)。
下列手動備援說明適用互動模式；自動模式會提前載入 OCR，辨識失敗或網站拒絕時停止。

## 執行方式

本次已建立的 Windows CPython 3.13.5 環境：

```powershell
.\.venv\windows\Scripts\python.exe -m pip install -r requirements-automation-lock.txt
.\.venv\windows\Scripts\python.exe -m thsr_ticket.main --browser chrome --auto-captcha --check-connection
.\.venv\windows\Scripts\python.exe -m thsr_ticket.main --browser chrome --auto-captcha --query-only
.\.venv\windows\Scripts\python.exe -m thsr_ticket.main --browser chrome --auto-captcha
```

第二行只讀取首頁及圖片，不 POST、不詢問個資、不建立訂位。
第三行可送出車次查詢，但會在選車及填寫個資前停止；第四行才啟動互動訂票流程。
不加 `--auto-captcha` 就完全使用手動驗證碼。不加 `--browser` 則沿用 HTTP 模式。
可見 Chrome 是本次能取得實站頁面的組合；背景模式不是已驗證可用的替代方案。

## 實作

- 一般視窗模式以標準方式啟動已安裝的 Chrome／Edge，再透過
  [Playwright CDP 連線](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp) 操作。
  依照 [Chrome 的隔離設定檔要求](https://developer.chrome.com/blog/remote-debugging-port)，
  每次建立專用暫存設定檔，開發者連線僅使用 localhost。
  不載入個人設定檔、歷史紀錄或登入資料；結束時關閉程式自己的瀏覽器並清理暫存設定檔。
  清理前檢查目錄位置與前綴，拒絕刪除其他目錄。
- 背景模式仍使用 Playwright 的瀏覽器啟動方式，主要用於離線測試；未確認能完成實站查詢。
- 處理高鐵首次開啟時的 Cookie／個人資料使用說明，避免遮罩阻擋查詢按鈕。
- 保留同一瀏覽器工作階段，用原生選單、輸入、單選及按鈕操作填表；隱藏的出發／回程日期會同步更新日期元件。
  不會重新觸發未變更的 select 選項，避免額外 AJAX；工作階段隱藏欄位沿用網站值。
- 讀取瀏覽器已收到的原始驗證碼圖片，不額外請求一張新圖，也不使用可能受遮罩影響的畫面截圖。
- 使用 [ddddocr](https://github.com/sml2h3/ddddocr) 1.6.1 在本機推論，不將圖片傳至第三方服務。
  模型延遲載入並重用，未安裝選用套件時不影響手動模式。
- 解碼時合併英文字母大小寫分數，去除 CTC 重複／空白，僅接受四碼 ASCII 英數字。
  每碼模型分數最低值須達 0.5；此門檻是工程篩選條件，**不是實測準確率，也不是成功機率保證**。
- 格式不符、低分或模型載入失敗會改為手動輸入。網站拒絕 OCR 查詢後，本次執行停用 OCR。
- HTTP 模式也修正了網站 hidden fields 覆蓋使用者指定日期的問題。
- 傳輸層不會自動重送查詢／訂票 POST；後續自動模式可在無符合車次時建立新一輪查詢，但不重送最終訂位。

## 驗證結果

| 項目 | 結果 |
| --- | --- |
| 原 HTTP 模式 | 先前測試讀取逾時 |
| 背景 Chrome、背景 Edge | 訂票頁連線重設；一般官網可讀取 |
| Playwright 啟動的一般視窗／專用一般設定檔 | 可以取得首頁，但查詢 POST 仍曾逾時 |
| 標準啟動 Chrome + CDP | 查詢收到 302 → 200 回應，成功解析網站驗證碼錯誤及車次結果 |
| 現行表單欄位 | 確認座位選項值為 0/1/2、動態查詢 radio 值，以及出發日期是 hidden input |
| 本機 OCR | 人工圖片可辨識；實站圖片有四碼候選，也有低分／格式不符而退回手動的情況 |
| 原啟動方式的追加診斷 | 等待 document readyState=complete，確認送出的站點、日期、時間與票數正確，延長至 45 秒仍未取得回應 |
| 修正後實站查詢 | 標準啟動模式下，OCR 自動填碼，網站接受查詢並回傳 10 筆車次；沒有手動輸入驗證碼 |
| 實際訂票 | 未執行：沒有選車、輸入個資或送出最終訂票 |
| 離線 pytest（含背景與標準 Chrome 攔截測試） | 85 通過，1 項實站 HTTP 測試預設跳過；涵蓋兩種啟動模式及暫存資料清理 |
| Flake8、pip check | 通過 |

少量測試中，OCR 單次推論約 0.01–0.15 秒，依圖片與是否包含初始化而不同。
這不是端到端訂票速度比較，樣本也不足以估計高鐵圖片辨識率。

離線瀏覽器測試會攔截所有頁面請求，涵蓋 Cookie 遮罩、同一張圖片只取一次、隱藏欄位、
出發日期、未選單選項目不觸發事件，以及失敗 POST 不重送。
真實頁面、圖片與診斷腳本放在 Git 忽略的 `.venv/` 中，沒有納入版本控制。

成功查詢測試使用台北 → 左營、2026/09/26、09:30 起、成人一張。
網站回傳 10 筆車次，解析結果包含 0829、0643、0645。程式在列表頁停止，沒有選車或建立訂位。
標準啟動模式也曾正常收到「檢測碼輸入錯誤」回覆，表示 OCR 尚不能保證每次正確。
這次比對確認不同啟動方式有不同結果，未逐一隔離啟動參數，因此不認定某一個參數或某一項網站檢測就是唯一原因。

## 尚待完成

1. 首頁、OCR、車次列表已經實站驗證；選車後的個資頁及最終訂票仍只有離線測試，未建立真實訂位。
2. 用具人工標註、數量足夠的圖片評估辨識率與門檻，再決定是否需高鐵專用模型。
3. 先前紀錄中的全專案 mypy／pylint 與 CI 問題仍待整理，本次未宣稱它們已通過。

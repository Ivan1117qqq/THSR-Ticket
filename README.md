# 高鐵訂票小幫手

**!!--純研究用途，請勿用於不當用途--!!**

此程式提供另一種輕便的方式訂購高鐵車票，操作介面為命令列介面。相較於使用網頁訂購，本程式因為省卻了渲染網頁介面的時間，只保留最核心的訂購功能，因此能省下大量等待的時間。

**(2025/05/12 update)** 另有 Rust 新版本提供執行檔、早鳥票預訂、會員購票等新功能，可以參考 [thsr-ticket-rs](https://github.com/BreezeWhite/thsr-ticket-rs)

## 執行

本程式由python語言所寫成，因此必須先安裝python才能夠使用。官方下載網址[點這裡](https://www.python.org/downloads/release/python-381/)

### 方法一 （快速）
在已經有安裝好python的環境下，執行以下指令
``` bash
pip install git+https://github.com/BreezeWhite/THSR-Ticket.git

# 執行
thsr-ticket
```

### 方法二
首先先將程式碼下載到本機，執行以下指令或是直接按右上方的下載按鈕

```
git clone https://github.com/BreezeWhite/THSR-Ticket.git
```

再來進入到資料夾中

```
cd THSR-Ticket
```

安裝必要的套件

```
python -m pip install -r requirements.txt
```

最後執行程式

```
python thsr_ticket/main.py
```

### 本機驗證與測試

2026/09/25 已在 Windows、CPython 3.13.5 驗證安裝與離線流程。
本次完整結果與尚待確認事項見 [驗證紀錄](docs/verification.md)。
`requirements-lock.txt` 記錄本次驗證使用的套件版本（Python 3.13 環境）。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\thsr-ticket.exe --help
.\.venv\Scripts\python.exe -m pytest -q
```

預設測試不連線。若要檢查高鐵首頁、表單及驗證碼是否仍可讀取：

```powershell
.\.venv\Scripts\python.exe -m pytest thsr_ticket/unittest/test_http_request.py --live -q
```

此連線測試只讀取頁面，不送出訂票。離線測試採用人工建立的 HTML 範例，
通過不代表已確認現行網站可以完成訂票。

身分證與手機預設不保存；訂票完成後可選擇保存至 `thsr_ticket/.db/history.json`。
此檔案是明文 JSON，歷史紀錄列表只顯示證號與手機末三碼。


## 注意事項!!!

本程式依舊有許多尚未完成的部分，僅具備基本訂購的功能，若是僅需要訂購成人票、且無特殊需求者，此程式對您而言是加速訂購流程的方便小工具。不符合以上描述者，目前仍建議使用官方網頁進行訂購。

#### 提供功能

- [x] 選擇啟程、到達站
- [x] 選擇出發日期、時間
- [x] 選擇班次
- [x] 選擇成人、孩童、愛心、敬老與大學生票數（資格與可售票種由網站判定）
- [x] 輸入驗證碼
- [x] 輸入身分證字號
- [x] 輸入手機號碼
- [x] 保留此次輸入紀錄，下次可快速選擇此次紀錄
- [x] 選擇車廂種類與座位喜好
- [x] 查詢錯誤後重新取得驗證碼；選車時輸入 0 重新查詢

#### 未提供功能

以下功能為未提供輸入的選項，但程式具備相關功能，可依照自身需求、對程式進行修改

- [ ] 訂位方式(依時間搜尋車次/直接輸入車次號碼)
- [ ] 僅顯示早鳥優惠票

#### 未完成功能

- [ ] 同一頁內直接更換認證碼（目前透過重新查詢取得）
- [ ] 語音播放認證碼
- [ ] 輸入護照號碼
- [ ] 輸入市話
- [ ] 輸入電子郵件
- [ ] 會員購票

# 發行、依賴與版本管理

目前版本為 0.4.0，交付未簽章 Windows 安裝包。變更摘要見 [CHANGELOG](../CHANGELOG.md)，測試證據與限制見 [驗證紀錄](verification.md)。

2026-10-23 的歷史診斷與桌面通知仍是未發行原始碼，尚未重建這份安裝包。正式發行時需更新版本、重新打包並執行自我檢查與通知人工驗收，不能把舊產物的驗證當成新功能已打包通過。

## 唯一版本來源

只修改 `thsr_ticket/version.py` 的 `VERSION`。`setup.py` 從同一檔案取得 Python 套件版本；`scripts/release_metadata.py` 產生以下建置產物：

- `build/release/version_info.txt`：Windows EXE 的數值及文字版本。
- `build/release/version.iss`：Inno Setup 使用的 `AppVersion`。
- `build/release/metadata.json`：版本與安裝包檔名。
- 完成安裝包後，以 `--finalize` 產生 `dist/release.json` 與安裝包旁的 `.sha256`。

`TravelDesk.spec` 會在打包前呼叫產生器。安裝腳本引用產生的 include；CI 從 `dist/release.json` 取得檔名，不另外寫死版本。原有的 `installer/version_info.txt` 已移除，請勿另建一份手動版本資源。

## 依賴分類

| 用途 | 安裝清單 | 說明 |
| --- | --- | --- |
| HTTP／手動驗證碼執行環境 | `requirements-lock.txt` | 固定基本執行依賴，不含開發工具。 |
| 瀏覽器與 OCR | `requirements-automation-lock.txt` | 引用基本執行依賴，加入 Playwright、OCR 及其依賴。 |
| Qt 桌面 | `requirements-desktop.txt` | 引用自動化依賴，固定 Qt 與 shiboken 版本。 |
| 開發與測試 | `requirements-dev.txt` | 引用基本執行依賴及 `requirements-dev-lock.txt`；測試 Qt 時另外安裝桌面清單。 |
| EXE 打包 | `requirements-build.txt` | 引用桌面清單，加入 PyInstaller 與建置依賴，不包含 pytest／Flake8。 |

`requirements.txt` 保留基本執行依賴範圍，供 Python 套件 metadata 使用；`requirements-automation.txt` 是選用套件的直接依賴。`setup.py` 重用這些清單，避免 extras 另外寫一組版本。產品 wheel 不包含專案測試套件。

本次固定版本延用已驗證的 Windows CPython 3.13 環境，沒有順便升級第三方套件。這些 lock 沒有逐檔 hash，也不宣稱已驗證所有 Python／OS 組合。調整依賴時需在乾淨環境執行 `pip check`、相關測試及打包自我檢查。

## 一般發行建置

在專案根目錄，準備包含桌面、打包及開發工具的環境：

```powershell
.\.venv\windows\Scripts\python.exe -m pip install -r requirements-build.txt -r requirements-dev.txt
.\scripts\build_release.ps1 -Python .\.venv\windows\Scripts\python.exe -Compiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

腳本依序執行完整桌面必測、Flake8、PyInstaller、Inno Setup 及 hash／metadata 產生。若使用不含開發工具的獨立建置環境，先在測試環境完成必測，再使用 `-SkipTests`；此參數只略過測試，不代表已驗收。

分開執行時：

```powershell
python -m scripts.release_metadata
python -m PyInstaller TravelDesk.spec --noconfirm
ISCC.exe installer/TravelDesk.iss
python -m scripts.release_metadata --finalize
```

產物為整個 `dist/TravelDesk/`、`dist/installer/TravelDesk-Setup-0.4.0.exe`、旁附 `.sha256` 及 `dist/release.json`。後續版本的檔名由 VERSION 自動改變。`signed: false` 表示本流程交付未簽章版本；未來加入簽章時，應在最終簽章後重新計算 hash，並另行更新簽章資訊。

## 安裝驗收與既有安裝保護

`scripts/test_installer.ps1` 預設使用正式 AppId；偵測到已安裝版本會拒絕測試，不會覆蓋使用者正在使用的程式。沒有 `-PreviousInstaller` 時只驗證同版本覆裝；有此參數才會檢查舊、新版本不同並執行升級。

本機已有正式安裝時，使用 `scripts/installer_fixture.py` 由相同安裝模板產生不同 AppId 的測試包。工具會核對 payload EXE 版本，限制產物留在 `build/`，並更換應用名稱、捷徑與預設資料夾；測試包停用壓縮，不能作為正式交付包。

```powershell
python -m scripts.installer_fixture --payload dist/TravelDesk --version 0.4.0 --output build/installer-test/new
ISCC.exe build/installer-test/new/isolated.iss
```

真正的舊版升級需先保留舊 payload，於重建 EXE 前產生舊版測試包，再以相同測試 AppId 產生新版：

```powershell
.\scripts\test_installer.ps1 `
  -Installer build/installer-test/new/TravelDesk-Setup-0.4.0.exe `
  -PreviousInstaller build/installer-test/old/TravelDesk-Setup-0.3.3.exe `
  -AppId AC67957F-3FE3-43AC-A675-23228CC39418
```

不要將正式安裝包搭配測試 AppId 使用；AppId 必須與實際產生的安裝包一致。腳本檢查安裝／解除安裝的執行中保護、安裝後自我檢查，以及安裝目錄內與外部假設定、state、task、runs、備份、操作清單的 hash 保留，最後輸出 `build/installer-smoke-*/validation.json`。

這是安裝器保留資料的驗證，不會讓正式 GUI 讀取假資料，也不等於已驗證所有版本的資料格式轉換。本機不同 AppId 驗收不能取代正式 AppId 在獨立乾淨 Windows 的驗收。

## 發行前仍需確認

保留測試報告、安裝自我檢查、升級與解除安裝報告，以及 hash 對應的變更說明。手動 Windows workflow 會驗證安裝包 hash 與 EXE 版本並保存報告；目前不自動發布 GitHub Release。每次遠端執行的結果仍需另行確認，不能用本機成功取代。

官網查票、訂位及取消相容性另行驗收；本文件的自我檢查與安裝測試只使用暫存假資料。

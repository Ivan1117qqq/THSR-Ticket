import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName:'backupDialog'
    required property var backend
    readonly property var manager:backend.backup
    title:'完整備份與還原'
    anchors.centerIn:parent
    modal:true
    width:Math.min(850, parent.width-40)
    height:Math.min(650, parent.height-40)
    closePolicy:Popup.NoAutoClose
    contentItem:ColumnLayout {
        spacing:16
        Caption {text:dialog.manager.message; color:dialog.manager.error.code ? '#a33b30' : '#30445c'}
        Caption {visible:!!dialog.manager.error.code; text:dialog.manager.error.guidance || ''; color:'#a33b30'}
        ProgressBar {Layout.fillWidth:true; indeterminate:true; visible:dialog.manager.busy}
        TabBar {
            id:tabs; objectName:'backupTabs'; Layout.fillWidth:true
            enabled:!dialog.manager.busy; padding:4; spacing:4
            background:Rectangle {radius:14; color:'#f4f6fa'}
            SegmentTab {text:'建立備份'}
            SegmentTab {text:'還原備份'}
        }
        ScrollView {
            id:body
            Layout.fillWidth:true; Layout.fillHeight:true
            clip:true; contentWidth:availableWidth
            ColumnLayout {
                width:body.availableWidth; spacing:16
                Caption {text:tabs.currentIndex === 0 ? '備份目前已儲存的設定、訂位狀態、執行／封存紀錄、歷史備份及操作清單。' : '驗證備份後還原到新的子資料夾，不覆寫目前設定或既有訂位。'}
                Flow {
                    Layout.fillWidth:true; spacing:10
                    AppButton {visible:tabs.currentIndex === 0; text:'預覽目前資料'; enabled:!dialog.manager.busy; onClicked:dialog.manager.previewSource()}
                    AppButton {visible:tabs.currentIndex === 1; text:'選擇備份檔'; enabled:!dialog.manager.busy; onClicked:dialog.manager.chooseArchive()}
                    AppButton {visible:tabs.currentIndex === 1; text:'選擇還原位置'; enabled:dialog.manager.canChooseDestination; onClicked:dialog.manager.chooseDestination()}
                }
                Caption {visible:tabs.currentIndex === 1 && dialog.manager.archivePath !== ''; text:'備份檔'}
                TextEdit {visible:tabs.currentIndex === 1 && dialog.manager.archivePath !== ''; text:dialog.manager.archivePath; Layout.fillWidth:true; readOnly:true; selectByMouse:true; wrapMode:Text.WrapAnywhere; color:'#30445c'}
                Caption {visible:tabs.currentIndex === 1 && dialog.manager.targetPath !== ''; text:dialog.manager.restoredPath !== '' ? '已還原的資料夾' : '將建立的新資料夾'}
                TextEdit {visible:tabs.currentIndex === 1 && dialog.manager.targetPath !== ''; text:dialog.manager.targetPath; Layout.fillWidth:true; readOnly:true; selectByMouse:true; wrapMode:Text.WrapAnywhere; color:'#30445c'}
                Card {
                    Layout.fillWidth:true
                    visible:!!dialog.manager.summary.files && dialog.manager.summary.mode === (tabs.currentIndex === 0 ? 'source' : 'archive')
                    title:(dialog.manager.summary.files || 0) + ' 個檔案 · ' + Number(dialog.manager.summary.bytes || 0).toLocaleString(Qt.locale(),'f',0) + ' bytes'
                    Flow {
                        Layout.fillWidth:true; spacing:16
                        Repeater {
                            model:[['configuration','設定'],['state','防重送狀態'],['task','任務摘要'],['runs','執行與封存'],['history-backups','歷史備份'],['operations','操作清單'],['config-backups','設定備份']]
                            delegate:Text {
                                required property var modelData
                                text:modelData[1] + ' ' + ((dialog.manager.summary.groups || {})[modelData[0]] || 0)
                                color:'#53716c'; font.pixelSize:13
                            }
                        }
                    }
                    Caption {text:dialog.manager.summary.has_state ? '包含原防重送紀錄；還原後仍須核對原訂位狀態。' : '原備份沒有防重送紀錄。'}
                    Caption {text:dialog.manager.summary.protection === 'windows-dpapi' ? '設定含 Windows 保護欄位，還原不會解密或轉成明文；載入需要原 Windows 環境。' : '設定可能含明文個資；格式損壞或不支援時，還原會保留原始內容。'}
                }
            }
        }
        Caption {visible:tabs.currentIndex === 1 && dialog.manager.summary.mode === 'archive' && !dialog.manager.summary.has_state; color:'#a7532e'; text:'沒有原防重送檔，還原時會建立「待核對」狀態；確認官網後才能訂下一筆。'}
        Caption {visible:tabs.currentIndex === 1 && dialog.manager.restoredPath !== '' && dialog.backend.dirty; text:'目前設定有未儲存變更，請先儲存，再載入還原設定。'}
        Caption {text:'完整備份包含個資與訂位代碼，ZIP 未整體加密，請妥善保管。'}
        RowLayout {
            Item {Layout.fillWidth:true}
            AppButton {text:'取消預覽'; visible:dialog.manager.cancellable; onClicked:dialog.manager.cancel()}
            AppButton {objectName:'exportBackupButton'; text:'備份到新檔案'; primary:true; visible:tabs.currentIndex === 0; enabled:dialog.manager.canExport; onClicked:dialog.manager.chooseExport()}
            AppButton {objectName:'restoreBackupButton'; text:'確認還原到新資料夾'; primary:true; visible:tabs.currentIndex === 1 && dialog.manager.restoredPath === ''; enabled:dialog.manager.canRestore; onClicked:dialog.manager.applyRestore()}
            AppButton {objectName:'openRestoredButton'; text:'開啟還原資料夾'; visible:tabs.currentIndex === 1 && dialog.manager.restoredPath !== ''; onClicked:dialog.manager.openRestoredFolder()}
            AppButton {objectName:'loadRestoredButton'; text:'載入還原設定'; primary:true; visible:tabs.currentIndex === 1 && dialog.manager.restoredPath !== ''; enabled:!dialog.backend.running && !dialog.backend.dirty; onClicked:if(dialog.backend.loadRestored()) dialog.close()}
            AppButton {text:'返回'; enabled:!dialog.manager.busy; onClicked:dialog.close()}
        }
    }
}

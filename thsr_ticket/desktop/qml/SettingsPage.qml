import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: page
    objectName: 'settingsPage'
    required property var backend
    property alias section: tabs.currentIndex
    signal storageRequested()
    signal historyRequested()
    signal diagnosticsRequested()
    signal backupRequested()
    signal retentionRequested()
    signal ocrRequested()
    clip: true
    contentWidth: availableWidth

    ColumnLayout {
        width: page.availableWidth
        spacing: 20
        Item {height:8}
        TabBar {
            id: tabs
            objectName: 'settingsTabs'
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
            padding:4; spacing:4
            background:Rectangle {radius:14; color:'white'; border.color:'#e2e8ef'}
            SegmentTab {objectName:'generalSettingsTab'; text:'一般偏好'}
            SegmentTab {text:'資料管理'}
            SegmentTab {text:'進階與關於'}
        }
        Loader {
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
            sourceComponent:tabs.currentIndex === 0 ? general : tabs.currentIndex === 1 ? data : advanced
        }
        Item {height:12}
    }

    Component {
        id: general
        ColumnLayout {
            spacing:20
            Card {
                Layout.fillWidth:true; title:'桌面通知'; subtitle:'任務完成後，從桌面直接回到結果。'
                RowLayout {
                    Layout.fillWidth:true
                    PreferenceSwitch {
                        objectName:'notificationSwitch'; text:'啟用任務通知'
                        checked:page.backend.tools.notificationsEnabled
                        onClicked:page.backend.tools.setNotifications(checked)
                    }
                    Item {Layout.fillWidth:true}
                    AppButton {
                        objectName:'testNotificationButton'; text:'測試通知'
                        enabled:page.backend.tools.notificationsEnabled && page.backend.tools.notificationsAvailable
                        onClicked:page.backend.tools.testNotification()
                    }
                }
                Caption {text:page.backend.tools.notificationsAvailable ? '偏好立即保存。通知不含個資；關閉 App 後任務不會繼續執行。' : '目前系統不支援通知；偏好仍可保存。'}
                Caption {visible:page.backend.tools.notificationsEnabled && page.backend.tools.notificationsAvailable; text:'未看到通知時，請檢查 Windows 通知與勿擾設定。'}
            }
            Card {
                Layout.fillWidth:true; title:'繳費期限提醒'; subtitle:'App 開啟期間，提醒即將到期的本機訂位。'
                PreferenceSwitch {
                    objectName:'paymentReminderSwitch'; text:'啟用繳費期限提醒'
                    checked:page.backend.planner.remindersEnabled
                    onClicked:page.backend.planner.setReminders(checked,page.backend.planner.leadMinutes)
                }
                RowLayout {
                    Caption {text:'提前提醒'}
                    ComboBox {
                        objectName:'paymentReminderLead'; Accessible.name:'繳費期限提前提醒時間'
                        model:['1 小時','3 小時','1 天']; implicitHeight:42
                        currentIndex:[60,180,1440].indexOf(page.backend.planner.leadMinutes)
                        onActivated:page.backend.planner.setReminders(page.backend.planner.remindersEnabled,[60,180,1440][currentIndex])
                    }
                }
                Caption {text:'需同時啟用桌面通知。期限必須有完整日期與時間；可從總覽待辦核對並設定本機期限。關閉 App 後不會提醒。'}
                Caption {text:page.backend.planner.reminderMessage; visible:text!==''}
            }
            Card {
                Layout.fillWidth:true; title:'個人資料保護'
                PreferenceSwitch {
                    objectName:'privacySwitch'; text:'以 Windows 帳號保護證號與手機'
                    checked:page.backend.protectPrivate
                    enabled:page.backend.protectionAvailable && !page.backend.running
                    onClicked:page.backend.setProtection(checked)
                }
                Caption {text:page.backend.protectionAvailable ? '變更後按上方「儲存設定」套用。受保護欄位需要原 Windows 帳號才能讀取。' : '目前環境不支援 Windows 個資保護。'}
                CheckBox {id:privacyHelp; text:'查看保護範圍與搬移說明'}
                Caption {visible:privacyHelp.checked; text:'只保護設定內的證號與手機，訂位結果及既有備份仍需妥善保管。跨帳號搬移前，請先在原帳號解除保護並儲存，再於目的帳號重新啟用。'}
            }
        }
    }
    Component {
        id: data
        ColumnLayout {
            spacing:20
            Card {
                Layout.fillWidth:true; title:'目前行程設定'; subtitle:'載入設定會沿用其訂位紀錄與防重送狀態。'
                Flow {
                    Layout.fillWidth:true; spacing:10
                    AppButton {text:'載入設定'; enabled:!page.backend.running; onClicked:page.backend.load()}
                    AppButton {text:'另存設定'; enabled:!page.backend.running; onClicked:page.backend.saveAs()}
                    AppButton {text:'開啟資料夾'; onClicked:page.backend.folder()}
                    AppButton {text:'完整備份與還原'; enabled:!page.backend.running; onClicked:page.backupRequested()}
                }
                CheckBox {id:pathDetails; text:'顯示檔案位置'}
                TextEdit {visible:pathDetails.checked; readOnly:true; text:page.backend.configPath; Layout.fillWidth:true; wrapMode:Text.WrapAnywhere; color:'#30445c'; selectByMouse:true}
            }
            Card {
                Layout.fillWidth:true; title:'歷史紀錄'; subtitle:'整理本機資料，保留每次操作的還原方式。'
                AppButton {text:'開啟資料管理'; enabled:!page.backend.running; onClicked:page.storageRequested()}
                AppButton {text:'保留期限與永久清理'; enabled:!page.backend.running; onClicked:page.retentionRequested()}
                Caption {text:'移至備份不會取消官網訂位，也不會釋放磁碟空間。'}
            }
        }
    }
    Component {
        id: advanced
        ColumnLayout {
            spacing:20
            Card {
                Layout.fillWidth:true; title:'問題診斷'; subtitle:'選擇本次狀態，或查看過去任務的失敗階段。'
                Flow {
                    Layout.fillWidth:true; spacing:10
                    AppButton {text:'本次診斷匯出'; onClicked:page.diagnosticsRequested()}
                    AppButton {text:'歷史任務診斷'; onClicked:page.historyRequested()}
                    AppButton {text:'檢查執行環境'; enabled:!page.backend.running; onClicked:page.backend.tools.checkEnvironment()}
                    AppButton {text:'OCR 標註與評估'; enabled:!page.backend.running; onClicked:page.ocrRequested()}
                }
                Caption {text:'匯出前可預覽；診斷不包含個資、訂位代碼或完整日誌。'}
            }
            Card {
                Layout.fillWidth:true; title:'Travel Desk'; subtitle:'版本 ' + page.backend.version + ' · Qt Quick'
                Caption {text:'使用本機 Chrome 與 OCR；訂位完成即停止，不付款。'}
                Caption {text:page.backend.tools.updateMessage; visible:text !== ''}
                RowLayout {
                    AppButton {text:page.backend.tools.updateChecking ? '檢查中…' : '檢查更新'; enabled:!page.backend.running && !page.backend.tools.updateChecking; onClicked:page.backend.tools.checkUpdates()}
                    AppButton {text:'開啟發行頁'; visible:page.backend.tools.updateAvailable; onClicked:page.backend.tools.releasePage()}
                }
            }
        }
    }
}

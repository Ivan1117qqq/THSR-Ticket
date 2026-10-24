import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    required property var backend
    visible: true
    width: 1280; height: 880
    minimumWidth: 1080; minimumHeight: 720
    title: 'Travel Desk · 雙鐵旅程'
    color: '#f4f6fa'
    font.family: 'Microsoft JhengHei UI'
    font.pixelSize: 14
    property var pageTitles: ['旅程總覽', '安排新行程', '任務進度', '我的訂位', '偏好與資料']
    property bool allowClose: false
    onClosing: function(close) { close.accepted = allowClose; if (!allowClose) backend.requestClose() }
    Connections {
        target: backend
        function onCloseReady() { window.allowClose = true; window.close() }
        function onConfirmRequested(action) { unsavedDialog.action = action; unsavedDialog.open() }
        function onStorageRecoveryDetected() { storageDialog.openRecovery() }
        function onValidationFailed(field) { backend.navigate(1) }
    }


    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: 218; Layout.fillHeight: true
            color: '#142b3a'
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 8
                Rectangle {
                    width: 42; height: 42; radius: 12; color: '#285346'
                    Text { anchors.centerIn: parent; text: 'T'; color: '#b7f0d2'; font.pixelSize: 25; font.bold: true }
                    Layout.topMargin: 16
                }
                Text { text: 'Travel Desk'; color: 'white'; font.pixelSize: 23; font.bold: true; Layout.topMargin: 12 }
                Text { text: '雙鐵旅程管理'; color: '#8ba6b7'; font.pixelSize: 12; Layout.bottomMargin: 35 }
                Repeater {
                    model: ['旅程總覽', '新增行程', '任務進度', '我的訂位', '設定']
                    delegate: Button {
                        required property int index
                        required property string modelData
                        objectName: 'navigation_' + index
                        text: modelData
                        Accessible.name: modelData
                        activeFocusOnTab: true
                        Layout.fillWidth: true; implicitHeight: 48
                        hoverEnabled: true
                        contentItem: RowLayout {
                            spacing:12
                            NavIcon {kind:index; ink:backend.page === index ? '#c2f4dc' : '#a7b7c5'; Layout.leftMargin:12}
                            Text {
                                text: modelData; color: backend.page === index ? '#c2f4dc' : '#a7b7c5'
                                font.pixelSize: 14; font.bold: backend.page === index; Layout.fillWidth:true
                            }
                        }
                        background: Rectangle {
                            radius: 10; color: backend.page === index ? '#254a48' : parent.hovered ? '#203d4f' : 'transparent'
                            border.width: parent.activeFocus ? 1 : 0; border.color: '#79b9b0'
                        }
                        onClicked: backend.navigate(index)
                    }
                }
                Item { Layout.fillHeight: true }
                Rectangle { Layout.fillWidth: true; height: 1; color: '#294251' }
                Text { text: '●  ' + backend.task.title; color: '#94cdb8'; font.pixelSize: 12; Layout.topMargin: 14; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                Text { text: 'DESKTOP  /  ' + backend.version; color: '#648093'; font.pixelSize: 10; Layout.bottomMargin: 8 }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Rectangle {
                Layout.fillWidth: true; implicitHeight: 94; color: 'white'
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 32; anchors.rightMargin: 32
                    ColumnLayout {
                        spacing: 5
                        Text { text: 'WORKSPACE  /  ' + String(backend.page + 1).padStart(2,'0'); color: '#8a98aa'; font.pixelSize: 10; font.letterSpacing: 1.5 }
                        Text { text: window.pageTitles[backend.page] + (backend.dirty ? ' · 未儲存' : ''); color: '#20334b'; font.pixelSize: 23; font.bold: true }
                    }
                    Item { Layout.fillWidth: true }
                    AppButton { text: '載入設定'; visible:backend.page === 1; quiet: true; enabled: !backend.running; onClicked: backend.load() }
                    AppButton { text: '儲存設定'; visible:backend.page === 1 || (backend.page === 4 && backend.dirty); enabled: !backend.running; onClicked: backend.save() }
                }
            }
            StackLayout {
                currentIndex: backend.page
                Layout.fillWidth: true; Layout.fillHeight: true

                OverviewPage {
                    backend:window.backend
                    onTemplatesRequested:templateDialog.open()
                    onDeadlineRequested:deadlineDialog.showRecord(record)
                }

                JourneyPage {
                    backend:window.backend
                    onTemplatesRequested:templateDialog.open()
                    onDualRequested:dualRailDialog.open()
                }

                ProgressPage {
                    backend:window.backend
                    onDualRequested:dualRailDialog.open()
                }

                BookingsPage {
                    backend:window.backend
                    onCancelRequested:managementDialog.showRecord(record)
                    onArchiveRequested:recordActions.showArchive(record)
                    onResolveRequested:recordActions.showResolution(record)
                }

                SettingsPage {
                    backend:window.backend
                    onStorageRequested:{backend.prepareStorage(); storageDialog.open()}
                    onHistoryRequested:{backend.tools.prepareHistory(); historyDialog.open()}
                    onDiagnosticsRequested:{backend.tools.prepareDiagnostics(); diagnosticDialog.open()}
                    onBackupRequested:backupDialog.open()
                    onRetentionRequested:retentionDialog.open()
                    onOcrRequested:ocrLabDialog.open()
                }
            }
            Rectangle {
                visible:backend.page === 1
                Layout.fillWidth:true; implicitHeight:84; color:'white'
                RowLayout {
                    anchors.fill:parent; anchors.leftMargin:28; anchors.rightMargin:28; spacing:12
                    ColumnLayout {
                        Text {text:backend.form.start_station + ' → ' + backend.form.dest_station; color:'#20334b'; font.bold:true; font.pixelSize:16}
                        Text {text:backend.form.outbound_date + '  ·  ' + backend.form.class_type + '車廂'; color:'#8390a2'; font.pixelSize:12}
                    }
                    Item {Layout.fillWidth:true}
                    AppButton {text:'只查票'; enabled:!backend.running; onClicked:backend.start(true)}
                    AppButton {text:backend.task.can_book ? '自動訂位 · 不付款' : '請先處理目前任務'; primary:true; enabled:backend.task.can_book; onClicked:backend.start(false)}
                }
            }
            Rectangle {
                Layout.fillWidth:true; implicitHeight:Math.max(48, statusText.implicitHeight+24)
                color:backend.error ? '#fff0e8' : '#eaf2f1'
                Text {id:statusText; anchors {left:parent.left; right:recoveryButton.left; verticalCenter:parent.verticalCenter; margins:28}
                    text:backend.status; color:backend.error ? '#a7532e' : '#53716c'; font.pixelSize:12; wrapMode:Text.WordWrap}
                AppButton {id:recoveryButton; anchors.right:parent.right; anchors.rightMargin:16; anchors.verticalCenter:parent.verticalCenter
                    visible:backend.recovery !== ''; text:backend.recovery === 'records' ? '核對訂位' : backend.recovery === 'settings' ? '檢查環境' : backend.recovery === 'official' ? '開啟官網' : '調整設定'
                    onClicked:backend.recover(); implicitHeight:36}
            }
        }
    }
    BookingActions {id:recordActions; backend:window.backend; anchors.fill:parent}
    HistoryDialog {
        id:historyDialog; objectName:'historyDiagnosticsDialog'; tools:backend.tools; anchors.centerIn:parent
        onPreviewRequested:if(backend.tools.prepareHistoricalDiagnostics()) diagnosticDialog.open()
    }
    DiagnosticDialog {id:diagnosticDialog; tools:backend.tools; anchors.centerIn:parent}
    StorageDialog {id:storageDialog; backend:window.backend; anchors.centerIn:parent}
    UnsavedDialog {id:unsavedDialog; backend:window.backend; anchors.centerIn:parent}
    BackupDialog {backend:window.backend; id:backupDialog}
    ManagementDialog {backend:window.backend; id:managementDialog}
    RetentionDialog {backend:window.backend; id:retentionDialog}
    OcrLabDialog {backend:window.backend; id:ocrLabDialog}
    TemplateDialog {backend:window.backend; id:templateDialog}
    DeadlineDialog {backend:window.backend; id:deadlineDialog}
    DualRailDialog {backend:window.backend; id:dualRailDialog}
}

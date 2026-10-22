import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    required property var backend
    signal previewRequested()
    component Caption: Text {
        color:'#78869a'; font.pixelSize:12; wrapMode:Text.WordWrap
        Layout.fillWidth:true
    }
    title: '歷史任務診斷'
    modal: true
    width: Math.min(920, parent.width - 40)
    height: Math.min(650, parent.height - 40)
    closePolicy: Popup.NoAutoClose
    contentItem: ColumnLayout {
        spacing: 12
        Caption {Layout.fillWidth:true; text:dialog.backend.historyDiagnostics.message}
        ProgressBar {Layout.fillWidth:true; visible:dialog.backend.historyDiagnostics.busy; indeterminate:true}
        Caption {Layout.fillWidth:true; text:'依紀錄修改時間顯示最近 200 次任務，包含歷史備份。每份最多讀取末端 4 MB、顯示 200 筆簡化事件。'}
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:20
            Rectangle {
                Layout.preferredWidth:320; Layout.fillHeight:true
                color:'#f5f7fb'; radius:12; border.color:'#e5eaf1'
                ListView {
                    anchors.fill:parent; anchors.margins:8; clip:true; spacing:6
                    model:dialog.backend.historyDiagnostics.rows
                    ScrollBar.vertical:ScrollBar {}
                    delegate:ItemDelegate {
                        required property var modelData
                        width:ListView.view.width
                        highlighted:dialog.backend.historyDiagnostics.selected.id === modelData.id
                        onClicked:dialog.backend.historyDiagnostics.select(modelData.id)
                        contentItem:ColumnLayout {
                            spacing:6
                            Text {text:modelData.date; color:'#78869a'; font.pixelSize:12}
                            Text {text:modelData.title; color:'#20334b'; font.pixelSize:15; font.bold:true; Layout.fillWidth:true; wrapMode:Text.WordWrap}
                            Text {text:modelData.phase; color:'#53716c'; font.pixelSize:12}
                        }
                    }
                    Text {anchors.centerIn:parent; visible:parent.count === 0; text:'尚無可顯示的任務'; color:'#78869a'}
                }
            }
            ScrollView {
                id: details
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true; contentWidth:availableWidth
                ColumnLayout {
                    width:details.availableWidth; spacing:18
                    Text {text:dialog.backend.historyDiagnostics.selected.title || '選擇一筆任務'; color:'#20334b'; font.pixelSize:22; font.bold:true; Layout.fillWidth:true; wrapMode:Text.WordWrap}
                    Caption {Layout.fillWidth:true; text:dialog.backend.historyDiagnostics.selected.phase ? '最後階段 · ' + dialog.backend.historyDiagnostics.selected.phase : '從左側選擇，即可查看原因與下一步。'}
                    Caption {Layout.fillWidth:true; visible:!!dialog.backend.historyDiagnostics.selected.id; text:'執行版本 · ' + (dialog.backend.historyDiagnostics.selected.recorded_version === 'unknown' ? '未記錄' : (dialog.backend.historyDiagnostics.selected.recorded_version || '未記錄'))}
                    Text {text:dialog.backend.historyDiagnostics.selected.guidance || ''; color:'#30445c'; font.pixelSize:14; Layout.fillWidth:true; wrapMode:Text.WordWrap}
                    Caption {Layout.fillWidth:true; visible:!!dialog.backend.historyDiagnostics.selected.partial; text:'這份紀錄不完整或已截取部分內容，請搭配目前任務及官網狀態判斷。'}
                    AppButton {text:'預覽與匯出診斷'; enabled:!!dialog.backend.historyDiagnostics.selected.id && !dialog.backend.historyDiagnostics.busy; onClicked:dialog.previewRequested()}
                    Caption {Layout.fillWidth:true; text:'診斷不包含證號、手機、訂位代碼、車次或私人路徑。這裡不會修改、刪除或取消任何訂位。'}
                }
            }
        }
        RowLayout {
            Item {Layout.fillWidth:true}
            AppButton {text:'取消讀取'; visible:dialog.backend.historyDiagnostics.busy; onClicked:dialog.backend.historyDiagnostics.cancel()}
            AppButton {text:'重新讀取'; enabled:!dialog.backend.historyDiagnostics.busy; onClicked:dialog.backend.prepareHistory()}
            AppButton {text:'返回'; enabled:!dialog.backend.historyDiagnostics.busy; onClicked:dialog.close()}
        }
    }
}

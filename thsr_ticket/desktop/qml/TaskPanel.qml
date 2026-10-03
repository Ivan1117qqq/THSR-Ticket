import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Card {
    id: panel
    required property var backend
    property color accent: ({'neutral':'#486079','active':'#147d70','success':'#147d70',
                             'warning':'#9b6417','danger':'#b54b3d'})[backend.task.tone] || '#486079'
    border.color: backend.task.tone === 'warning' ? '#e7cda6' : '#dce7e7'
    RowLayout {
        Layout.fillWidth: true
        Rectangle {
            implicitWidth: 40; implicitHeight: 40; radius: 12; color: Qt.alpha(panel.accent, 0.1)
            Text {anchors.centerIn: parent; text: panel.backend.running ? '…' : panel.backend.task.tone === 'warning' || panel.backend.task.tone === 'danger' ? '!' : panel.backend.task.tone === 'success' ? '✓' : '•'; color:panel.accent; font.pixelSize:24; font.bold:true}
        }
        Text {text:panel.backend.task.title; font.pixelSize:22; font.bold:true; color:panel.accent; Layout.fillWidth:true; wrapMode:Text.WordWrap}
        Text {text:panel.backend.running ? '即時任務' : '本機狀態'; font.pixelSize:12; color:'#7e8ca0'}
    }
    Text {text:backend.task.detail; color:'#51677f'; font.pixelSize:14; wrapMode:Text.WordWrap; Layout.fillWidth:true}
    RowLayout {
        visible:backend.running; Layout.fillWidth:true; spacing:8
        Repeater {
            model:['準備','等待時間','查詢車次','選擇車次','送出與確認']
            delegate: Rectangle {
                required property int index
                required property string modelData
                Layout.fillWidth:true; implicitHeight:34; radius:8
                color:index === panel.backend.task.step ? '#def1eb' : '#f2f5f8'
                Text {anchors.centerIn:parent; text:modelData; font.pixelSize:12; color:index === panel.backend.task.step ? '#147d70' : '#7e8ca0'}
            }
        }
    }
    RowLayout {
        AppButton {text:panel.backend.task.label; primary:true; visible:!(panel.backend.running && panel.backend.page === 2); onClicked:panel.backend.taskAction()}
        AppButton {visible:!panel.backend.running && !panel.backend.task.can_book; text:'開啟官網'; onClicked:panel.backend.official()}
        AppButton {visible:panel.backend.running; text:'停止任務'; enabled:panel.backend.task.code !== 'stopping'; onClicked:panel.backend.stop()}
    }
}

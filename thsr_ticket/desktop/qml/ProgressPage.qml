import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    required property var backend
    id: progressPage
    clip:true; contentWidth:availableWidth
    ColumnLayout {
        width:progressPage.availableWidth; spacing:20
        Item {height:8}
        TaskPanel {backend:progressPage.backend; Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28}
        Card {
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; title:'執行細節'
            RowLayout {
                Layout.fillWidth:true
                BusyIndicator {running:backend.running; visible:backend.running; implicitWidth:44; implicitHeight:44}
                Text {text:backend.phase; font.pixelSize:24; font.bold:true; color:'#20334b'; wrapMode:Text.WordWrap; Layout.fillWidth:true}
            }
            Caption {text:'第 ' + backend.attempt + ' 輪查詢  /  上限 ' + backend.form.max_attempts + ' 輪'}
            Text {visible:backend.countdown !== ''; text:backend.countdown; font.pixelSize:36; color:'#147d70'; font.bold:true}
            Caption {visible:backend.retryReason !== ''; text:backend.retryReason; Accessible.role:Accessible.StaticText; Accessible.name:text}
            Text {
                visible:!!backend.match.train_id
                text:'車次 ' + (backend.match.train_id || '') + '    ' + (backend.match.depart || '') + ' → ' + (backend.match.arrive || '')
                font.pixelSize:22; color:'#147d70'; font.bold:true
            }
            ProgressBar {Layout.fillWidth:true; indeterminate:backend.running; value:0}
            Caption {text:backend.form.start_station + ' → ' + backend.form.dest_station + '   ·   ' + backend.form.outbound_date}
            RowLayout {
                AppButton {visible:backend.running; text:'停止任務'; onClicked:backend.stop()}
                AppButton {text:backend.task.label; visible:!backend.running; onClicked:backend.taskAction()}
            }
        }
        Card {
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
            CheckBox {id:showLog; text:'顯示詳細執行紀錄'}
            TextArea {
                visible:showLog.checked; Layout.fillWidth:true; readOnly:true
                text:backend.log; wrapMode:TextEdit.Wrap; selectByMouse:true
                font.family:'Consolas'; font.pixelSize:12; color:'#4c6077'
            }
        }
        Item {height:12}
    }
}

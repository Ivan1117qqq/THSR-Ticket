import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    required property var backend
    id: overview
    clip: true; contentWidth: availableWidth
    ColumnLayout {
        width: overview.availableWidth; spacing: 22
        anchors.margins: 28
        Item { height: 6 }
        TaskPanel {backend:overview.backend; Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28}
        Rectangle {
            Layout.fillWidth: true; Layout.leftMargin: 28; Layout.rightMargin: 28; implicitHeight: 220
            radius: 20
            gradient: Gradient { orientation: Gradient.Horizontal; GradientStop {position:0; color:'#193e4c'} GradientStop {position:1; color:'#236a62'} }
            ColumnLayout {
                anchors {fill:parent; margins:28}
                spacing: 12
                Text { text: 'YOUR NEXT JOURNEY'; color: '#a2cfcd'; font.pixelSize: 11; font.letterSpacing: 2 }
                Text { text: backend.form.start_station + '   →   ' + backend.form.dest_station; color:'white'; font.pixelSize: 34; font.bold: true }
                Text { text: backend.form.outbound_date + '    ·    ' + backend.form.earliest_departure + ' — ' + backend.form.latest_departure; color:'#c3dddf'; font.pixelSize:15 }
                Item { Layout.fillHeight:true }
                AppButton { text:'編輯這段旅程  →'; onClicked:backend.navigate(1) }
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.leftMargin:28; Layout.rightMargin:28; spacing:18
            Card {
                Layout.fillWidth:true; title:'本次查詢'
                Text { text:String(backend.attempt) + ' 輪'; color:'#147d70'; font.pixelSize:28; font.bold:true }
                Caption { text: backend.phase }
                AppButton { text:'查看進度'; quiet:true; onClicked:backend.navigate(2) }
            }
            Card {
                Layout.fillWidth:true; title:'訂位紀錄'
                Text { text:String(backend.currentRecordCount) + ' 筆待處理'; color:'#20334b'; font.pixelSize:28; font.bold:true }
                Caption { text:'保留原票，封存本機紀錄後可安排下一筆。' }
                AppButton { text:'管理我的訂位'; quiet:true; onClicked:backend.navigate(3) }
            }
        }
        Caption { Layout.leftMargin:32; Layout.rightMargin:32; text:'設定行程 → 選擇查票或自動訂位 → 在我的訂位查看結果'; Layout.bottomMargin:24 }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    required property var backend
    id: overview
    objectName:'overviewPage'
    signal templatesRequested()
    signal deadlineRequested(var record)
    clip: true; contentWidth: availableWidth
    component Metric: Rectangle {
        required property string label
        required property int count
        property color ink:'#20334b'
        Layout.fillWidth:true; Layout.preferredWidth:1; implicitHeight:92
        radius:16; color:'white'; border.color:'#e5eaf1'
        RowLayout {
            anchors.fill:parent; anchors.margins:20
            Text {text:parent.parent.label; color:'#718398'; font.pixelSize:14; Layout.fillWidth:true}
            Text {text:String(parent.parent.count); color:parent.parent.ink; font.pixelSize:30; font.bold:true}
        }
    }
    ColumnLayout {
        width: overview.availableWidth; spacing: 18
        anchors.margins: 28
        Item { height: 6 }
        Rectangle {
            Layout.fillWidth: true; Layout.leftMargin: 28; Layout.rightMargin: 28; implicitHeight: 116
            radius: 20
            gradient: Gradient { orientation: Gradient.Horizontal; GradientStop {position:0; color:'#193e4c'} GradientStop {position:1; color:'#236a62'} }
            RowLayout {
                anchors {fill:parent; margins:24}
                spacing:16
                ColumnLayout {
                    Layout.fillWidth:true; spacing:8
                    Text {text:backend.form.start_station+'   →   '+backend.form.dest_station; color:'white'; font.pixelSize:27; font.bold:true}
                    Text {text:backend.form.outbound_date+' · '+backend.form.earliest_departure+' — '+backend.form.latest_departure; color:'#c3dddf'; font.pixelSize:13}
                }
                AppButton {text:'新增／編輯行程'; onClicked:backend.navigate(1)}
                AppButton {objectName:'overviewTemplatesButton'; text:'常用範本'; enabled:!backend.running; onClicked:overview.templatesRequested()}
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.leftMargin:28; Layout.rightMargin:28; spacing:18
            Metric {label:'繳費待辦'; count:backend.planner.agenda.payment; ink:'#147d70'}
            Metric {label:'待核對'; count:backend.planner.agenda.pending; ink:'#a96936'}
            Metric {label:'即將出發'; count:backend.planner.agenda.upcoming}
        }
        Rectangle {
            visible:backend.running || !backend.task.can_book
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; implicitHeight:64
            radius:14; color:'#eaf2f1'
            RowLayout {
                anchors.fill:parent; anchors.leftMargin:20; anchors.rightMargin:12
                Text {text:backend.task.title; color:'#53716c'; font.bold:true; Layout.fillWidth:true; wrapMode:Text.WordWrap}
                AppButton {text:backend.task.label; quiet:true; onClicked:backend.taskAction()}
            }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; spacing:18
            JourneyCalendar {backend:overview.backend; Layout.fillWidth:true; Layout.preferredWidth:1; Layout.alignment:Qt.AlignTop}
            AgendaCard {backend:overview.backend; Layout.fillWidth:true; Layout.preferredWidth:1; Layout.alignment:Qt.AlignTop; onDeadlineRequested:overview.deadlineRequested(record)}
        }
        Caption {Layout.leftMargin:32; Layout.rightMargin:32; text:'只顯示目前設定的本機紀錄；缺少年份且無法核對的日期不會放入月曆。'; Layout.bottomMargin:24}
    }
}

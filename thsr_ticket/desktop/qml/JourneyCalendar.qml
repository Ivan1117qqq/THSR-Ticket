import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Card {
    id: calendar
    required property var backend
    objectName:'journeyCalendarCard'
    readonly property var service: backend.planner
    title:'行程月曆'
    contentSpacing:10
    RowLayout {
        Layout.fillWidth:true
        AppButton {objectName:'previousJourneyMonth'; text:'‹'; Accessible.name:'上一個月'; implicitWidth:40; onClicked:calendar.service.moveMonth(-1)}
        AppButton {objectName:'journeyMonthTitle'; text:calendar.service.calendar.title; quiet:true; Accessible.name:'選擇行程月曆日期'; Layout.fillWidth:true; onClicked:monthDate.openDate(calendar.service.selectedDate)}
        AppButton {objectName:'nextJourneyMonth'; text:'›'; Accessible.name:'下一個月'; implicitWidth:40; onClicked:calendar.service.moveMonth(1)}
        AppButton {text:'今天'; quiet:true; onClicked:calendar.service.today()}
    }
    GridLayout {
        columns:7; columnSpacing:6; rowSpacing:6; Layout.fillWidth:true
        Repeater {
            model:['一','二','三','四','五','六','日']
            Text {required property string modelData; text:modelData; color:'#8390a2'; horizontalAlignment:Text.AlignHCenter; Layout.fillWidth:true; Layout.preferredWidth:1; Layout.minimumWidth:0; Layout.preferredHeight:26}
        }
        Repeater {
            objectName:'journeyCalendarCells'; model:calendar.service.calendar.cells
            Button {
                id: dayButton
                required property var modelData
                objectName:modelData.date ? 'journeyDay_'+modelData.date : ''
                Layout.fillWidth:true; Layout.preferredWidth:1; Layout.minimumWidth:0; implicitHeight:34; enabled:modelData.day>0
                Accessible.name:modelData.date+'，'+modelData.count+' 筆行程'
                contentItem:Column {
                    spacing:3
                    Text {text:dayButton.modelData.day || ''; color:dayButton.modelData.date===calendar.service.selectedDate ? '#12665d' : '#34465c'; font.bold:dayButton.modelData.count>0; horizontalAlignment:Text.AlignHCenter; width:parent.width}
                    Rectangle {width:5; height:5; radius:3; color:'#147d70'; visible:dayButton.modelData.count>0; anchors.horizontalCenter:parent.horizontalCenter}
                }
                background:Rectangle {radius:9; color:dayButton.modelData.date===calendar.service.selectedDate ? '#e3f2ed' : dayButton.hovered ? '#f1f5fa' : 'transparent'; border.width:dayButton.activeFocus ? 1 : 0; border.color:'#147d70'}
                onClicked:calendar.service.selectDate(modelData.date)
            }
        }
    }
    Line {}
    Caption {text:calendar.service.selectedDate+' · '+calendar.service.calendar.total+' 筆本機紀錄'}
    Repeater {
        model:calendar.service.calendar.items
        delegate:ColumnLayout {
            required property var modelData
            Layout.fillWidth:true; spacing:5
            Text {text:(modelData.time || '時間待核對')+'   '+modelData.route; color:'#20334b'; font.bold:true; Layout.fillWidth:true; wrapMode:Text.WordWrap}
            Caption {text:(modelData.train ? '車次 '+modelData.train+' · ' : '')+modelData.status}
        }
    }
    Caption {visible:calendar.service.calendar.total===0; text:'這一天沒有本機行程。'}
    AppButton {text:'查看全部訂位'; quiet:true; onClicked:backend.navigate(3)}
    DatePicker {id:monthDate; objectName:'journeyCalendarPicker'; titleText:'跳到行程日期'; onDateAccepted:function(value) {calendar.service.selectDate(value)}}
}

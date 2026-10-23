import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Card {
    id: card
    required property var backend
    signal deadlineRequested(var record)
    title:'待辦事項'
    subtitle:'目前設定及其本機歷史；付款狀態與期限仍以官網為準。'
    Repeater {
        model:backend.planner.agenda.items
        delegate:Rectangle {
            required property var modelData
            Layout.fillWidth:true; implicitHeight:body.implicitHeight+28; radius:12
            color:modelData.pending || modelData.expired ? '#fff3e9' : '#f5f8fb'
            ColumnLayout {
                id:body; anchors.left:parent.left; anchors.right:parent.right; anchors.top:parent.top; anchors.margins:14; spacing:8
                RowLayout {
                    Layout.fillWidth:true
                    Text {text:modelData.pending ? '訂位結果待核對' : '繳費待辦'; color:modelData.pending || modelData.expired ? '#9c572f' : '#147d70'; font.bold:true}
                    Item {Layout.fillWidth:true}
                    Text {text:modelData.date || '日期待核對'; color:'#718398'; font.pixelSize:12}
                }
                Text {text:modelData.route; font.pixelSize:17; font.bold:true; color:'#20334b'; Layout.fillWidth:true; wrapMode:Text.WordWrap}
                Caption {visible:!modelData.pending; text:modelData.remaining+(modelData.local_deadline ? ' · 手動設定' : '')}
                RowLayout {
                    AppButton {text:'核對訂位'; quiet:true; onClicked:backend.navigate(3)}
                    AppButton {objectName:'editDeadline_'+modelData.id; text:'設定提醒期限'; visible:modelData.payable; enabled:!backend.running; onClicked:card.deadlineRequested(modelData)}
                }
            }
        }
    }
    Caption {visible:backend.planner.agenda.total===0; text:backend.recordsLoading ? '正在讀取訂位紀錄…' : '目前沒有繳費或核對待辦。'}
    Caption {visible:backend.planner.agenda.total>6; text:'顯示前 6 筆，共 '+backend.planner.agenda.total+' 筆；完整紀錄請至「我的訂位」。'}
}

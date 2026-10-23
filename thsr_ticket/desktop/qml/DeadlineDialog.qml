import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: 'deadlineDialog'
    required property var backend
    property var record: null
    function showRecord(value) {
        backend.planner.clearReminderMessage()
        record=value
        deadlineInput.text=value.deadline ? value.deadline.slice(0,16).replace('T',' ') : ''
        consent.checked=false
        open()
    }
    parent:Overlay.overlay; anchors.centerIn:parent; modal:true
    title:'設定本機繳費提醒'; width:Math.min(520,parent.width-48); padding:24
    background:Rectangle {radius:20; color:'white'; border.color:'#dce3ec'}
    contentItem:ColumnLayout {
        spacing:16
        Text {text:dialog.record ? dialog.record.route : ''; color:'#20334b'; font.pixelSize:20; font.bold:true}
        Caption {text:'官網原始期限：'+(dialog.record ? dialog.record.raw_deadline || '未記錄' : '')}
        RowLayout {
            Layout.fillWidth:true
            TextField {id:deadlineInput; objectName:'localDeadlineInput'; placeholderText:'YYYY-MM-DD HH:MM'; Accessible.name:'本機繳費提醒期限，台灣時間'; Layout.fillWidth:true; implicitHeight:44; selectByMouse:true}
            AppButton {text:'選日期'; onClicked:deadlineDate.openDate(deadlineInput.text)}
        }
        Caption {text:'台灣時間。只設定本機提醒，不會延長官網繳費期限。'}
        CheckBox {id:consent; objectName:'deadlineConsent'; text:'我已核對官網完整期限'; Layout.fillWidth:true}
        Caption {text:backend.planner.reminderMessage; visible:text!==''}
        RowLayout {
            AppButton {text:'取消'; quiet:true; onClicked:dialog.close()}
            AppButton {text:'移除手動期限'; visible:!!dialog.record && dialog.record.local_deadline; enabled:!backend.running; onClicked:{backend.planner.clearDeadline(dialog.record.id); dialog.close()}}
            Item {Layout.fillWidth:true}
            AppButton {objectName:'saveDeadlineButton'; text:'保存'; primary:true; enabled:consent.checked && !backend.running; onClicked:if(backend.planner.setDeadline(dialog.record.id,deadlineInput.text)) dialog.close()}
        }
    }
    DatePicker {id:deadlineDate; titleText:'選擇繳費期限日期'; onDateAccepted:function(value) {deadlineInput.text=value+' '+(deadlineInput.text.length>=16 ? deadlineInput.text.slice(11,16) : '12:00')}}
}

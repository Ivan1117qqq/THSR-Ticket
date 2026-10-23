import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    required property var backend
    property string action: ''
    id:unsavedDialog; title:'尚有未儲存的變更'; anchors.centerIn:parent; modal:true; width:490
    ColumnLayout {
        width:parent.width; spacing:20
        Caption {text:'請選擇是否儲存目前設定。取消會返回原畫面。'}
        RowLayout {
            AppButton {text:'取消'; onClicked:unsavedDialog.close()}
            AppButton {objectName:'discardUnsavedButton'; text:'不儲存'; onClicked:{unsavedDialog.close(); backend.confirmAction(unsavedDialog.action, 'discard')}}
            AppButton {text:'儲存後繼續'; primary:true; onClicked:{unsavedDialog.close(); backend.confirmAction(unsavedDialog.action, 'save')}}
        }
    }
}

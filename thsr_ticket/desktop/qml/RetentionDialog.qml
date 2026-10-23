import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id:dialog
    objectName:'retentionDialog'
    required property var backend
    readonly property var service:backend.retention
    title:'紀錄保留與永久清理'
    anchors.centerIn:parent; modal:true; closePolicy:Popup.NoAutoClose
    width:Math.min(700,parent.width-40)
    Connections {target:dialog.service; function onChanged() {consent.checked=false}}
    contentItem:ColumnLayout {
        spacing:16
        Caption {text:dialog.service.message}
        RowLayout {
            Caption {text:'保留最近天數'}
            SpinBox {id:days; from:1; to:3650; value:90; editable:true; enabled:!dialog.service.busy; Accessible.name:'紀錄保留天數'; onValueChanged:consent.checked=false}
            AppButton {text:'預覽可釋放空間'; enabled:!dialog.backend.running; onClicked:dialog.service.preview(days.value)}
        }
        ProgressBar {visible:dialog.service.busy; indeterminate:true; Layout.fillWidth:true}
        Card {
            visible:!!dialog.service.result.preview; Layout.fillWidth:true; title:'清理預覽'
            Caption {text:'符合條件 '+(dialog.service.result.count || 0)+' 筆 · '+Number(dialog.service.result.bytes || 0).toLocaleString(Qt.locale(),'f',0)+' bytes'}
            Caption {text:'截止：'+(dialog.service.result.cutoff || '')+'；保護／略過 '+(dialog.service.result.protected || 0)+'／'+(dialog.service.result.skipped || 0)+' 項'}
        }
        ScrollView {
            visible:!!dialog.service.result.preview; Layout.fillWidth:true; Layout.preferredHeight:120; clip:true
            TextArea {readOnly:true; selectByMouse:true; wrapMode:TextEdit.Wrap; Accessible.name:'待清理紀錄清單'; text:(dialog.service.result.entries || []).map(function(item){return item.date+' · '+item.bytes+' bytes · '+item.relative}).join('\n') + (dialog.service.result.more ? '\n另有 '+dialog.service.result.more+' 筆，依同一期限清理。' : '')}
        }
        Caption {text:'只刪除已結束且過期的純查票日誌。訂位結果、封存狀態、操作證據及未知檔案保留；有目前訂位狀態時停止清理。'}
        CheckBox {id:consent; text:'我了解永久刪除無法還原，已核對上述數量及期限'; enabled:!!dialog.service.result.preview && dialog.service.result.days===days.value && !dialog.service.busy}
        RowLayout {
            AppButton {objectName:'permanentCleanupButton'; text:'永久刪除這些查票日誌'; enabled:consent.checked && consent.enabled && dialog.service.result.count>0; onClicked:dialog.service.apply(consent.checked)}
            AppButton {text:dialog.service.busy ? (dialog.service.cancellable ? '取消預覽' : '清理中，請等待') : '返回'; enabled:!dialog.service.busy || dialog.service.cancellable; onClicked:{if(dialog.service.busy) dialog.service.cancel(); else dialog.close()}}
        }
    }
}

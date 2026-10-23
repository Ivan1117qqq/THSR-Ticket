import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    required property var tools
    id:diagnosticDialog; objectName:'diagnosticDialog'; title:'診斷資料預覽'; anchors.centerIn:parent; modal:true; width:Math.min(600, parent.width - 40)
    contentItem:ColumnLayout {
        Caption {text:tools.diagnosticDescription}
        ScrollView {
            Layout.fillWidth:true; Layout.preferredHeight:300; clip:true
            TextArea {text:tools.diagnosticPreview; readOnly:true; selectByMouse:true; wrapMode:TextEdit.WrapAnywhere}
        }
        RowLayout {
            Item {Layout.fillWidth:true}
            AppButton {text:'返回'; onClicked:diagnosticDialog.close()}
            AppButton {text:'確認匯出'; primary:true; onClicked:tools.exportDiagnostics()}
        }
    }
}

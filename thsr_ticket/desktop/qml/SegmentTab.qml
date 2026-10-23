import QtQuick
import QtQuick.Controls

TabButton {
    id: control
    implicitHeight:44
    activeFocusOnTab:true
    hoverEnabled:true
    Accessible.name:text
    contentItem:Text {
        text:control.text; font.pixelSize:14; font.bold:control.checked
        color:control.checked ? '#146e64' : '#667b90'
        horizontalAlignment:Text.AlignHCenter; verticalAlignment:Text.AlignVCenter
    }
    background:Rectangle {
        radius:10
        color:control.checked ? '#e5f2ef' : control.hovered ? '#f0f4f8' : 'transparent'
        border.color:control.activeFocus ? '#147d70' : 'transparent'
    }
}

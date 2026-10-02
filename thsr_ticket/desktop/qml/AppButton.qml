import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    property bool quiet: false
    implicitHeight: 44
    horizontalPadding: 20
    font.family: 'Microsoft JhengHei UI'
    font.pixelSize: 14
    font.bold: primary
    hoverEnabled: true
    contentItem: Text {
        text: control.text
        font: control.font
        color: !control.enabled ? '#99a5b4' : control.primary ? 'white' : '#30445c'
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 10
        color: !control.enabled ? '#edf0f4' : control.primary ? (control.hovered ? '#12665d' : '#147d70') :
               control.hovered ? '#eaf0f5' : control.quiet ? 'transparent' : 'white'
        border.width: control.activeFocus ? 2 : control.primary || control.quiet ? 0 : 1
        border.color: control.activeFocus ? '#45b6a6' : '#dce3ec'
        Behavior on color { ColorAnimation { duration: 120 } }
    }
}

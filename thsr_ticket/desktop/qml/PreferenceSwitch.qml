import QtQuick
import QtQuick.Controls

Switch {
    id: control
    implicitHeight:44
    spacing:12
    activeFocusOnTab:true
    Accessible.name:text
    indicator:Rectangle {
        implicitWidth:44; implicitHeight:24
        x:control.leftPadding; y:(control.height-height)/2; radius:12
        color:!control.enabled ? '#e2e7ed' : control.checked ? '#147d70' : '#c9d4df'
        border.color:control.activeFocus ? '#20334b' : 'transparent'
        Rectangle {
            x:control.checked ? parent.width-width-3 : 3; y:3
            width:18; height:18; radius:9; color:'white'
        }
    }
    contentItem:Text {
        text:control.text; font.pixelSize:14
        color:control.enabled ? '#30445c' : '#99a5b4'
        leftPadding:control.indicator.width+control.spacing
        verticalAlignment:Text.AlignVCenter
    }
}

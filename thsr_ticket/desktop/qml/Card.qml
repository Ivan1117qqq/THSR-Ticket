import QtQuick
import QtQuick.Layouts

Rectangle {
    id: card
    default property alias contents: body.data
    property string title: ''
    property string subtitle: ''
    implicitHeight: body.implicitHeight + 48
    radius: 18
    color: 'white'
    border.color: '#e5eaf1'
    ColumnLayout {
        id: body
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 24 }
        spacing: 18
        Text { visible: card.title !== ''; text: card.title; font.pixelSize: 18; font.bold: true; color: '#20334b' }
        Text {
            visible: card.subtitle !== ''; text: card.subtitle; font.pixelSize: 12; color: '#78869a'
            Layout.fillWidth: true; wrapMode: Text.WordWrap
        }
    }
}
